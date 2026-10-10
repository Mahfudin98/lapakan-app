"""Tes yang menyentuh database berjalan di database TERPISAH ('<nama>_test').

Alasannya: worker memantau tabel scrape_jobs. Job uji berstatus 'queued' di database utama bisa
diambil worker sungguhan dan memicu scraping ke Google. Database terpisah juga melindungi data asli.
Bila PostgreSQL tidak terjangkau, tes DB otomatis di-skip.
"""
import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# wilayah minimal untuk tes (Provinsi Jawa Barat > Kota Bandung > Kec. Andir)
SEED_REGIONS = [
    ("32", "JAWA BARAT", 1, None),
    ("3273", "KOTA BANDUNG", 2, "32"),
    ("3273180", "ANDIR", 3, "3273"),
    ("3273140", "CICENDO", 3, "3273"),
]


def _prepare_test_database() -> None:
    from sqlalchemy.engine import make_url

    from app.config import get_settings

    url = make_url(get_settings().database_url)
    if not url.database or url.database.endswith("_test"):
        return
    test_db = f"{url.database}_test"
    try:
        import psycopg

        with psycopg.connect(
            host=url.host, port=url.port, user=url.username, password=url.password,
            dbname="postgres", autocommit=True, connect_timeout=3,
        ) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,)).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{test_db}"')
    except Exception:  # PostgreSQL tidak tersedia: biarkan tes DB di-skip
        return

    os.environ["DATABASE_URL"] = url.set(database=test_db).render_as_string(hide_password=False)
    get_settings.cache_clear()

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")

    from sqlalchemy.dialects.postgresql import insert

    from app.db import SessionLocal
    from app.models import Region

    with SessionLocal() as db:
        db.execute(
            insert(Region).values(
                [dict(kode=k, nama=n, level=lv, parent_kode=p) for k, n, lv, p in SEED_REGIONS]
            ).on_conflict_do_nothing()
        )
        db.commit()


_prepare_test_database()
