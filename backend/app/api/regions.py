from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Region
from app.services.planner import PlanError, load_chain

router = APIRouter(prefix="/regions", tags=["regions"])


class RegionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kode: str
    nama: str
    level: int
    parent_kode: str | None


@router.get("", response_model=list[RegionOut])
def list_regions(
    db: Annotated[Session, Depends(get_db)],
    level: Annotated[int | None, Query(ge=1, le=4, description="1=provinsi … 4=desa")] = None,
    parent: Annotated[str | None, Query(description="kode wilayah induk")] = None,
    q: Annotated[str | None, Query(description="cari nama (substring)")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    stmt = select(Region).order_by(Region.nama).limit(limit)
    if level is not None:
        stmt = stmt.where(Region.level == level)
    if parent is not None:
        stmt = stmt.where(Region.parent_kode == parent)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Region.nama.ilike(f"%{escaped}%", escape="\\"))
    return db.scalars(stmt).all()


class RegionDetail(RegionOut):
    path: list[RegionOut]  # dari provinsi sampai wilayah ini


@router.get("/{kode}", response_model=RegionDetail)
def get_region(kode: str, db: Annotated[Session, Depends(get_db)]):
    try:
        chain = load_chain(db, kode)
    except PlanError as exc:
        raise HTTPException(404, str(exc)) from exc
    last = chain[-1]
    return RegionDetail(
        kode=last.kode, nama=last.nama, level=last.level, parent_kode=last.parent_kode,
        path=[RegionOut.model_validate(r) for r in chain],
    )
