"""Filter + pengurutan tempat (dipakai oleh daftar, peta, facet, dan ekspor)."""
import uuid
from typing import Literal

from fastapi import HTTPException
from geoalchemy2 import Geography, Geometry
from pydantic import BaseModel, Field
from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.orm import Session

from app.models import JobPlace, Place

SortKey = Literal["skor", "terdekat", "terpopuler", "rating", "nama", "terbaru"]
RegionFilter = Literal["all", "hide_outside", "inside_only"]


class PlaceFilters(BaseModel):
    q: str | None = Field(None, description="cari nama")
    job_id: uuid.UUID | None = None
    region_kode: str | None = Field(None, pattern=r"^\d{1,10}$", description="termasuk wilayah di bawahnya")
    kategori: list[str] = Field(default=[], description="kategori Google (cocok persis), boleh banyak")
    min_rating: float | None = Field(None, ge=0, le=5)
    min_reviews: int | None = Field(None, ge=0)
    has_phone: bool = False
    has_website: bool = False
    hide_closed: bool = Field(False, description="sembunyikan yang tutup permanen")
    region_filter: RegionFilter = Field(
        "all", description="hide_outside = sembunyikan in_region=false; inside_only = hanya in_region=true"
    )


class PlaceQuery(PlaceFilters):
    sort: SortKey = "skor"
    lat: float | None = Field(None, ge=-90, le=90, description="titik acuan jarak")
    lng: float | None = Field(None, ge=-180, le=180)
    m: int | None = Field(None, ge=0, le=10_000, description="bobot prior skor Bayesian")


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def conditions(f: PlaceFilters, skip_kategori: bool = False) -> list:
    c = []
    if f.q and f.q.strip():
        c.append(Place.nama.ilike(_like(f.q.strip()), escape="\\"))
    if f.job_id:
        c.append(Place.id.in_(select(JobPlace.place_id).where(JobPlace.job_id == f.job_id)))
    if f.region_kode:
        c.append(Place.region_kode.like(f.region_kode + "%"))
    if f.kategori and not skip_kategori:
        c.append(Place.kategori_google.in_(f.kategori))
    if f.min_rating is not None:
        c.append(Place.rating >= f.min_rating)
    if f.min_reviews is not None:
        c.append(Place.review_count >= f.min_reviews)
    if f.has_phone:
        c.append(Place.telepon.isnot(None) & (Place.telepon != ""))
    if f.has_website:
        c.append(Place.website.isnot(None) & (Place.website != ""))
    if f.hide_closed:
        c.append(Place.status_bisnis.is_distinct_from("closed_permanently"))
    if f.region_filter == "hide_outside":
        c.append(Place.in_region.is_distinct_from(False))
    elif f.region_filter == "inside_only":
        c.append(Place.in_region.is_(True))
    return c


def average_rating(db: Session, f: PlaceFilters) -> float:
    """C pada rumus Bayesian: rata-rata rating seluruh hasil yang sedang difilter."""
    avg = db.scalar(select(func.avg(Place.rating)).where(*conditions(f), Place.rating.isnot(None)))
    return float(avg) if avg is not None else 0.0


def lat_expr():
    return func.ST_Y(cast(Place.geom, Geometry))


def lng_expr():
    return func.ST_X(cast(Place.geom, Geometry))


def distance_km_expr(lat: float, lng: float):
    ref = cast(func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326), Geography)
    return func.ST_Distance(Place.geom, ref) / 1000.0


def score_expr(c: float, m: float):
    v = cast(Place.review_count, Float)
    return case(
        (
            Place.review_count.isnot(None) & Place.rating.isnot(None),
            (v / (v + m)) * Place.rating + (m / (v + m)) * c,
        ),
        else_=None,
    )


def build_select(db: Session, q: PlaceQuery, default_m: int):
    """Return (stmt, meta). Kolom: Place, lat, lng, distance_km, score."""
    has_ref = q.lat is not None and q.lng is not None
    if q.sort == "terdekat" and not has_ref:
        raise HTTPException(422, "urutan 'terdekat' membutuhkan titik acuan (lat & lng)")
    m = q.m if q.m is not None else default_m
    c = average_rating(db, q)

    dist = distance_km_expr(q.lat, q.lng) if has_ref else cast(None, Float)
    score = score_expr(c, m)
    stmt = select(
        Place, lat_expr().label("lat"), lng_expr().label("lng"),
        dist.label("distance_km"), score.label("score"),
    ).where(*conditions(q))

    order = {
        "skor": [score.desc().nulls_last(), Place.rating.desc().nulls_last(), Place.review_count.desc().nulls_last()],
        "terdekat": [dist.asc().nulls_last()] if has_ref else [],
        "terpopuler": [Place.review_count.desc().nulls_last(), Place.rating.desc().nulls_last()],
        "rating": [Place.rating.desc().nulls_last(), Place.review_count.desc().nulls_last()],
        "nama": [func.lower(Place.nama).asc()],
        "terbaru": [Place.last_scraped_at.desc()],
    }[q.sort]
    stmt = stmt.order_by(*order, Place.id)  # id = tie-breaker agar pagination stabil
    return stmt, {"avg_rating": round(c, 3), "m": m}
