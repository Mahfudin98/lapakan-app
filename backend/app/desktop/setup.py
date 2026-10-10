"""Setup awal edisi desktop: membuat database lokal dan mengisinya. Aman dijalankan berulang.

    python -m app.desktop.setup [--progress-file FILE] [--skip-browser-download]

Dipanggil oleh installer (saat instalasi) dan oleh peluncur bila setup belum lengkap (penyembuhan otomatis).
Keluaran progres (stdout dan --progress-file), satu baris per kejadian:
    STEP|<n>|<total>|<pesan>     kemajuan
    WARN|<pesan>                 peringatan yang tidak menghentikan setup
    DONE                         berhasil
    ERROR|<pesan>                gagal (rincian lengkap di logs/setup.log)
Kode keluar 0 = berhasil, 1 = gagal.
"""
import argparse
import csv
import gzip
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from app.desktop import APP_VERSION, browser, config
from app.desktop.paths import Layout, release_aliases
from app.desktop.postgres import Postgres, PostgresError
from app.logging import setup_logging

TOTAL_STEPS = 8
MIN_REGIONS = 88_000  # dataset yang dibundel berisi 88.295 wilayah


class Reporter:
    def __init__(self, layout: Layout, progress_file: Path | None):
        self.layout = layout
        self.progress_file = progress_file
        layout.logs.mkdir(parents=True, exist_ok=True)
        self.logfile = open(layout.logs / "setup.log", "a", encoding="utf-8", buffering=1)
        self.logfile.write(f"\n===== setup {datetime.now():%Y-%m-%d %H:%M:%S} v{APP_VERSION} =====\n")

    def _emit(self, line: str) -> None:
        self.logfile.write(f"{datetime.now():%H:%M:%S} {line}\n")
        if sys.stdout is not None:
            try:
                print(line, flush=True)
            except Exception:  # noqa: BLE001 - konsol tertutup/encoding: jangan menggagalkan setup
                pass
        if self.progress_file:
            with open(self.progress_file, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def step(self, n: int, message: str) -> None:
        self._emit(f"STEP|{n}|{TOTAL_STEPS}|{message}")

    def warn(self, message: str) -> None:
        self._emit(f"WARN|{message}")

    def done(self) -> None:
        self._emit("DONE")

    def error(self, message: str) -> None:
        self._emit("ERROR|" + message.replace("\n", " ")[:900])

    def trace(self) -> None:
        self.logfile.write(traceback.format_exc() + "\n")


def migrate(layout: Layout) -> None:
    """alembic upgrade head terhadap database lokal (DATABASE_URL harus sudah diset)."""
    from alembic import command
    from alembic.config import Config

    ini = Config(str(layout.backend / "alembic.ini"))
    # ConfigParser memperlakukan '%' secara khusus; path pengguna bisa saja memuatnya
    ini.set_main_option("script_location", str(layout.backend / "alembic").replace("%", "%%"))
    command.upgrade(ini, "head")


def seed_regions_offline(layout: Layout) -> int:
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Region
    from app.scripts.seed_regions import save

    with SessionLocal() as db:
        have = db.scalar(select(func.count()).select_from(Region)) or 0
    if have >= MIN_REGIONS:
        return have
    if not layout.seed_regions.exists():
        raise FileNotFoundError(f"data wilayah bawaan tidak ditemukan: {layout.seed_regions}")
    with gzip.open(layout.seed_regions, "rt", encoding="utf-8", newline="") as fh:
        rows = [
            {"kode": r["kode"], "nama": r["nama"], "level": int(r["level"]), "parent_kode": r["parent_kode"] or None}
            for r in csv.DictReader(fh)
        ]
    if len(rows) < MIN_REGIONS:
        raise ValueError(f"data wilayah bawaan tidak lengkap ({len(rows)} baris)")
    save(rows)
    return len(rows)


def ensure_browser(layout: Layout, rep: Reporter, download: bool) -> None:
    found = browser.find_any()
    if found:
        rep._emit(f"INFO|browser ditemukan: {found}")
        return
    if not download:
        rep.warn("Microsoft Edge/Google Chrome tidak ditemukan. Scraping memerlukan salah satunya.")
        return
    rep.warn("Edge/Chrome tidak ditemukan; mengunduh Chromium (±150 MB), mohon tunggu…")
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(layout.browsers)}
    try:
        r = subprocess.run(
            [str(layout.python), "-m", "playwright", "install", "chromium"],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", timeout=900,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode != 0:
            rep.warn("Unduhan Chromium gagal; pasang Microsoft Edge atau Google Chrome. " + (r.stderr or "")[-200:])
    except Exception as exc:  # noqa: BLE001
        rep.warn(f"Unduhan Chromium gagal ({exc}); pasang Microsoft Edge atau Google Chrome.")


def is_complete(layout: Layout) -> bool:
    try:
        marker = json.loads(layout.setup_marker.read_text(encoding="utf-8"))
        return bool(marker.get("completed")) and layout.config_file.exists() and (layout.pgdata / "PG_VERSION").exists()
    except (OSError, ValueError):
        return False


def run_setup(layout: Layout, rep: Reporter, download_browser: bool = True) -> None:
    """Menjalankan semua langkah. Melempar exception bila gagal."""
    rep.step(1, "Memeriksa komputer")
    for needed in (layout.pg_bin / "initdb.exe", layout.backend / "alembic.ini", layout.seed_regions):
        if not needed.exists():
            raise FileNotFoundError(f"berkas aplikasi tidak lengkap: {needed}. Pasang ulang Peta Toko.")
    ensure_browser(layout, rep, download_browser)

    rep.step(2, "Menyiapkan folder data")
    layout.ensure_dirs()
    cfg = config.load(layout)
    if cfg is None:
        if layout.pgdata.exists() and any(layout.pgdata.iterdir()):
            # ada database lama tetapi konfigurasi (kata sandi) hilang: amankan, jangan hapus
            backup = layout.pgdata.with_name(f"pgdata.lama-{datetime.now():%Y%m%d-%H%M%S}")
            layout.pgdata.rename(backup)
            rep.warn(f"Konfigurasi hilang; database lama dipindahkan ke {backup.name}")
        cfg = config.new_config()
        config.save(layout, cfg)
    os.environ["DATABASE_URL"] = cfg.database_url
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    from app.config import get_settings

    get_settings.cache_clear()

    pg = Postgres(layout, cfg)
    rep.step(3, "Membuat database lokal (hanya sekali, ±1 menit)")
    pg.init()

    rep.step(4, "Menjalankan database")
    port_busy = pg.running_port() is None and not config.port_is_free(cfg.pg_port)
    if port_busy:
        cfg.pg_port = config.find_free_port(cfg.pg_port + 1, avoid=(cfg.app_port,))
        config.save(layout, cfg)
        os.environ["DATABASE_URL"] = cfg.database_url
        get_settings.cache_clear()
        pg = Postgres(layout, cfg)
    started_here = pg.running_port() != cfg.pg_port  # bila peluncur sudah menyalakannya, jangan dimatikan
    pg.start()
    try:
        rep.step(5, "Membuat basis data aplikasi")
        pg.ensure_database()

        rep.step(6, "Menyusun tabel")
        migrate(layout)

        rep.step(7, "Mengisi kategori toko")
        from app.scripts import seed_categories

        seed_categories.main()

        rep.step(8, "Mengisi data wilayah Indonesia (88 ribu desa/kelurahan)")
        n = seed_regions_offline(layout)
        rep._emit(f"INFO|{n} wilayah tersedia")
    finally:
        if started_here:
            pg.stop()  # setup selesai: database dimatikan; peluncur yang menyalakannya saat aplikasi dibuka

    layout.setup_marker.write_text(
        json.dumps({"completed": True, "version": APP_VERSION, "at": datetime.now().isoformat(timespec="seconds")}),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Setup database Peta Toko")
    ap.add_argument("--progress-file", type=Path)
    ap.add_argument("--skip-browser-download", action="store_true")
    args = ap.parse_args(argv)

    setup_logging("INFO")
    layout = Layout()
    layout.data.mkdir(parents=True, exist_ok=True)
    if args.progress_file and args.progress_file.exists():
        args.progress_file.unlink()
    rep = Reporter(layout, args.progress_file)
    try:
        try:
            run_setup(layout, rep, download_browser=not args.skip_browser_download)
        finally:
            release_aliases()  # setelah database dimatikan
    except (PostgresError, config.ConfigError, FileNotFoundError, ValueError) as exc:
        rep.trace()
        rep.error(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        rep.trace()
        rep.error(f"Terjadi kesalahan tak terduga: {type(exc).__name__}: {exc}")
        return 1
    rep.done()
    return 0


if __name__ == "__main__":
    sys.exit(main())
