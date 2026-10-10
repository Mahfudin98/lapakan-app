import csv
import io
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Place
from app.services import place_query as pq

router = APIRouter(prefix="/places", tags=["places"])
EXPORT_LIMIT = 50_000
MAP_LIMIT = 5_000


class PlaceOut(BaseModel):
    id: int
    nama: str
    kategori_google: str | None
    rating: float | None
    review_count: int | None
    alamat: str | None
    telepon: str | None
    website: str | None
    maps_url: str | None
    lat: float | None
    lng: float | None
    jam_buka: dict | None
    status_bisnis: str | None
    region_kode: str | None
    in_region: bool | None
    first_seen_at: datetime
    last_scraped_at: datetime
    distance_km: float | None = None
    score: float | None = None

    @field_validator("jam_buka", mode="before")
    @classmethod
    def _only_objects(cls, v):
        return v if isinstance(v, dict) else None  # data lama yang rusak tidak boleh membuat endpoint error


class ListMeta(BaseModel):
    avg_rating: float  # C pada rumus Bayesian
    m: int
    with_reviews: int  # jumlah hasil yang punya data jumlah ulasan
    outside_count: int = 0  # hasil (dengan filter lain) yang pasti di luar wilayah


class PlaceList(BaseModel):
    items: list[PlaceOut]
    total: int
    page: int
    page_size: int
    pages: int
    meta: ListMeta


class MapPoint(BaseModel):
    id: int
    nama: str
    lat: float
    lng: float
    rating: float | None
    review_count: int | None
    in_region: bool | None


class MapPoints(BaseModel):
    points: list[MapPoint]
    total: int
    truncated: bool


class Facet(BaseModel):
    kategori: str
    count: int


class ListQuery(pq.PlaceQuery):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)


class ExportQuery(pq.PlaceQuery):
    format: Literal["csv", "xlsx"] = "csv"


def _row_to_out(row) -> PlaceOut:
    p: Place = row.Place
    return PlaceOut(
        id=p.id, nama=p.nama, kategori_google=p.kategori_google, rating=p.rating,
        review_count=p.review_count, alamat=p.alamat, telepon=p.telepon, website=p.website,
        maps_url=p.maps_url, lat=row.lat, lng=row.lng, jam_buka=p.jam_buka,
        status_bisnis=p.status_bisnis, region_kode=p.region_kode, in_region=p.in_region,
        first_seen_at=p.first_seen_at, last_scraped_at=p.last_scraped_at,
        distance_km=row.distance_km, score=row.score,
    )


@router.get("", response_model=PlaceList)
def list_places(q: Annotated[ListQuery, Query()], db: Annotated[Session, Depends(get_db)]):
    page, page_size = q.page, q.page_size
    stmt, meta = pq.build_select(db, q, get_settings().bayesian_m)
    conds = pq.conditions(q)
    total = db.scalar(select(func.count()).select_from(Place).where(*conds)) or 0
    with_reviews = db.scalar(
        select(func.count(Place.review_count)).select_from(Place).where(*conds)
    ) or 0
    outside = db.scalar(
        select(func.count()).select_from(Place).where(
            *pq.conditions(q.model_copy(update={"region_filter": "all"})), Place.in_region.is_(False)
        )
    ) or 0
    rows = db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return PlaceList(
        items=[_row_to_out(r) for r in rows], total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)),
        meta=ListMeta(avg_rating=meta["avg_rating"], m=meta["m"], with_reviews=with_reviews, outside_count=outside),
    )


@router.get("/map", response_model=MapPoints)
def map_points(q: Annotated[pq.PlaceFilters, Query()], db: Annotated[Session, Depends(get_db)]):
    """Titik ringan untuk peta (tanpa pagination, maksimal 5.000)."""
    conds = pq.conditions(q) + [Place.geom.isnot(None)]
    total = db.scalar(select(func.count()).select_from(Place).where(*conds)) or 0
    rows = db.execute(
        select(
            Place.id, Place.nama, Place.rating, Place.review_count, Place.in_region,
            pq.lat_expr().label("lat"), pq.lng_expr().label("lng"),
        ).where(*conds).order_by(Place.id).limit(MAP_LIMIT)
    ).all()
    return MapPoints(
        points=[MapPoint(**r._mapping) for r in rows], total=total, truncated=total > MAP_LIMIT
    )


@router.get("/facets", response_model=list[Facet])
def facets(q: Annotated[pq.PlaceFilters, Query()], db: Annotated[Session, Depends(get_db)]):
    """Kategori Google yang ada di hasil (filter lain berlaku, filter kategori diabaikan)."""
    conds = pq.conditions(q, skip_kategori=True) + [Place.kategori_google.isnot(None)]
    rows = db.execute(
        select(Place.kategori_google, func.count().label("n")).where(*conds)
        .group_by(Place.kategori_google).order_by(func.count().desc(), Place.kategori_google).limit(60)
    ).all()
    return [Facet(kategori=r[0], count=r[1]) for r in rows]


# --- ekspor ------------------------------------------------------------------------------------
HEADERS = [
    "Nama", "Kategori", "Rating", "Jumlah ulasan", "Skor Bayesian", "Jarak (km)", "Alamat", "Telepon",
    "Website", "Latitude", "Longitude", "Google Maps", "Status", "Di dalam wilayah", "Terakhir di-scrape",
]
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _safe(value):
    """Cegah CSV/formula injection di Excel: awali sel teks berbahaya dengan apostrof."""
    if isinstance(value, str) and value.startswith(_DANGEROUS):
        return "'" + value
    return value


def _export_row(r) -> list:
    p: Place = r.Place
    in_region = {True: "ya", False: "tidak", None: "tidak diketahui"}[p.in_region]
    return [
        _safe(p.nama), _safe(p.kategori_google), p.rating, p.review_count,
        round(r.score, 3) if r.score is not None else None,
        round(r.distance_km, 2) if r.distance_km is not None else None,
        _safe(p.alamat), _safe(p.telepon), _safe(p.website),
        r.lat, r.lng, p.maps_url, p.status_bisnis, in_region,
        p.last_scraped_at.strftime("%Y-%m-%d %H:%M"),
    ]


@router.get("/export")
def export_places(q: Annotated[ExportQuery, Query()], db: Annotated[Session, Depends(get_db)]):
    format = q.format
    """Ekspor hasil yang sedang difilter & diurutkan (maksimal 50.000 baris)."""
    stmt, _ = pq.build_select(db, q, get_settings().bayesian_m)
    rows = db.execute(stmt.limit(EXPORT_LIMIT + 1)).all()
    truncated = len(rows) > EXPORT_LIMIT
    rows = rows[:EXPORT_LIMIT]
    name = f"peta-toko-{datetime.now():%Y%m%d-%H%M}.{format}"
    headers = {
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-Export-Truncated": "true" if truncated else "false",
        "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Truncated",
    }

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(HEADERS)
        for r in rows:
            w.writerow(_export_row(r))
        # BOM agar Excel membaca UTF-8 dengan benar
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Toko")
    ws.append(HEADERS)
    for r in rows:
        ws.append(_export_row(r))
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/{place_id}", response_model=PlaceOut)
def get_place(place_id: int, db: Annotated[Session, Depends(get_db)]):
    row = db.execute(
        select(
            Place, pq.lat_expr().label("lat"), pq.lng_expr().label("lng"),
            cast(None, Float).label("distance_km"), cast(None, Float).label("score"),
        ).where(Place.id == place_id)
    ).first()
    if row is None:
        raise HTTPException(404, "tempat tidak ditemukan")
    return _row_to_out(row)
