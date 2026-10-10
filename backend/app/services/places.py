from datetime import datetime, timedelta, timezone

from geoalchemy2 import Geography
from sqlalchemy import case, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import JobPlace, Place, QueryCache
from app.scraper.parser import PlaceData

# Kolom opsional: nilai baru menimpa hanya bila tidak NULL, supaya data hasil mode detail
# (telepon, website, ...) tidak hilang saat scrape berikutnya (mode daftar) tidak memuatnya.
_COALESCE_COLS = (
    "nama", "kategori_google", "rating", "review_count", "alamat", "telepon", "website",
    "maps_url", "geom", "region_kode", "in_region",
)


def upsert_place(
    db: Session, d: PlaceData, region_kode: str | None, in_region: bool | None
) -> tuple[int, bool]:
    """Upsert berdasar google_place_key. Return (place_id, baru?)."""
    geom = None
    if d.lat is not None and d.lng is not None:
        geom = cast(func.ST_SetSRID(func.ST_MakePoint(d.lng, d.lat), 4326), Geography)

    values = dict(
        google_place_key=d.google_place_key,
        nama=d.nama,
        kategori_google=d.kategori_google,
        rating=d.rating,
        review_count=d.review_count,
        alamat=d.alamat,
        telepon=d.telepon,
        website=d.website,
        maps_url=d.maps_url,
        geom=geom,
        jam_buka=d.jam_buka,
        status_bisnis=d.status_bisnis,
        region_kode=region_kode,
        in_region=in_region,
    )
    stmt = pg_insert(Place).values(**values)
    update = {c: func.coalesce(getattr(stmt.excluded, c), getattr(Place, c)) for c in _COALESCE_COLS}
    # gabung objek jam buka; hanya tipe 'object' yang digabung (JSON null/array dianggap kosong)
    old_obj = case((func.jsonb_typeof(Place.jam_buka) == "object", Place.jam_buka))
    new_obj = case((func.jsonb_typeof(stmt.excluded.jam_buka) == "object", stmt.excluded.jam_buka))
    update["jam_buka"] = func.coalesce(old_obj.op("||")(new_obj), new_obj, old_obj)
    update["status_bisnis"] = stmt.excluded.status_bisnis
    update["last_scraped_at"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=["google_place_key"], set_=update).returning(
        Place.id, literal_column("(xmax = 0)").label("inserted")
    )
    row = db.execute(stmt).one()
    return row.id, bool(row.inserted)


def link_places(db: Session, job_id, place_ids: list[int]) -> None:
    """Hubungkan job -> place (idempoten). ID yang sudah tidak ada di tabel places diabaikan."""
    if not place_ids:
        return
    existing = db.scalars(select(Place.id).where(Place.id.in_(place_ids))).all()
    if not existing:
        return
    stmt = pg_insert(JobPlace).values([{"job_id": job_id, "place_id": pid} for pid in existing])
    db.execute(stmt.on_conflict_do_nothing())


# --- cache query ------------------------------------------------------------------------------
def cache_key(query: str) -> str:
    return " ".join(query.lower().split())[:500]


def get_cached(
    db: Session, query: str, want_detail: bool, wanted_max: int, ttl_days: int
) -> list[int] | None:
    """Return daftar place_id bila cache masih valid, selain itu None."""
    row = db.get(QueryCache, cache_key(query))
    if row is None:
        return None
    if row.scraped_at < datetime.now(timezone.utc) - timedelta(days=ttl_days):
        return None
    if want_detail and not row.detail:
        return None
    if not row.complete and row.max_results < wanted_max:
        return None  # cache terpotong batas lebih kecil dari yang diminta sekarang
    return list(row.place_ids)


def put_cache(
    db: Session, query: str, detail: bool, max_results: int, complete: bool, place_ids: list[int]
) -> None:
    stmt = pg_insert(QueryCache).values(
        query_key=cache_key(query), detail=detail, max_results=max_results,
        complete=complete, place_ids=place_ids, scraped_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["query_key"],
        set_=dict(
            detail=stmt.excluded.detail, max_results=stmt.excluded.max_results,
            complete=stmt.excluded.complete, place_ids=stmt.excluded.place_ids,
            scraped_at=func.now(),
        ),
    )
    db.execute(stmt)
