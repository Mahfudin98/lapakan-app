import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import ScrapeJob
from app.services import planner

router = APIRouter(prefix="/jobs", tags=["jobs"])
ACTIVE = ("queued", "running")


class JobCreate(BaseModel):
    region_kode: str = Field(description="kode wilayah terpilih (level 1-4)")
    category_ids: list[int] = []
    keywords: list[str] = Field(default=[], description="kata kunci bebas")
    max_results: int | None = Field(None, ge=1, le=5000, description="batas total tempat per job")
    detail: bool = Field(False, description="klik tiap hasil (lebih lambat)")
    force_refresh: bool = Field(False, description="abaikan cache 7 hari")

    @model_validator(mode="after")
    def _need_keyword(self):
        if not self.category_ids and not [k for k in self.keywords if k.strip()]:
            raise ValueError("pilih minimal satu kategori atau isi kata kunci")
        return self


class QueryOut(BaseModel):
    keyword: str
    region_kode: str
    query: str


class PlanOut(BaseModel):
    total_queries: int
    keywords: list[str]
    queries: list[QueryOut]  # maksimal 50 pertama


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    params: dict
    progress: dict
    error: str | None
    created_at: datetime
    finished_at: datetime | None


def _plan(db: Session, body: JobCreate):
    try:
        return planner.plan_for_params(
            db, body.model_dump(), get_settings().scrape_max_queries
        )
    except planner.PlanError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/preview", response_model=PlanOut)
def preview(body: JobCreate, db: Annotated[Session, Depends(get_db)]):
    """Tampilkan query yang akan dijalankan tanpa membuat job."""
    plan, keywords = _plan(db, body)
    return PlanOut(
        total_queries=len(plan), keywords=keywords,
        queries=[QueryOut(keyword=p.keyword, region_kode=p.region_kode, query=p.query) for p in plan[:50]],
    )


def _create_row(db: Session, body: JobCreate) -> ScrapeJob:
    plan, keywords = _plan(db, body)
    params = body.model_dump()
    params["max_results"] = body.max_results or get_settings().scrape_max_results_default
    params["resolved_keywords"] = keywords
    job = ScrapeJob(
        params=params, status="queued",
        progress={"total_queries": len(plan), "done_queries": 0, "found": 0, "phase": "queued"},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("", response_model=JobOut, status_code=201)
def create_job(body: JobCreate, db: Annotated[Session, Depends(get_db)]):
    """Buat job berstatus 'queued'; worker (app.workers.runner) mengambilnya dari database."""
    return _create_row(db, body)


@router.get("", response_model=list[JobOut])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return db.scalars(select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(limit)).all()


def _get_or_404(db: Session, job_id: uuid.UUID) -> ScrapeJob:
    job = db.get(ScrapeJob, job_id)
    if job is None:
        raise HTTPException(404, "job tidak ditemukan")
    return job


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    return _get_or_404(db, job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    job = _get_or_404(db, job_id)
    if job.status not in ACTIVE:
        raise HTTPException(409, f"job sudah berstatus '{job.status}'")
    # selalu tandai permintaan batal (worker memeriksanya di antara aksi)
    db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(cancel_requested=True))
    # belum diambil worker: langsung batalkan (worker akan melewatinya)
    db.execute(
        update(ScrapeJob).where(ScrapeJob.id == job_id, ScrapeJob.status == "queued")
        .values(status="cancelled", finished_at=datetime.now(timezone.utc))
    )
    db.commit()
    db.refresh(job)
    return job
