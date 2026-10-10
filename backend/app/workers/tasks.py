"""Menjalankan satu ScrapeJob (dipanggil oleh app.workers.runner).

Aturan:
- `max_results` adalah batas TOTAL tempat unik per job (bukan per query).
- Query yang sama dalam `scrape_cache_days` hari memakai cache (tidak membuka browser).
- Captcha/blokir -> status "blocked", job berhenti. Tidak ada retry/bypass.
- Pembatalan lewat kolom `scrape_jobs.cancel_requested` (diset API), dicek di antara aksi.
"""
import asyncio
import time
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.config import get_settings
from app.db import SessionLocal
from app.logging import get_logger
from app.models import ScrapeJob
from app.scraper.maps import (
    BlockedError,
    MapsScraper,
    ScrapeConfig,
    ScrapeError,
)
from app.scraper.maps import CancelledError as JobCancelled
from app.services import planner
from app.services.places import get_cached, link_places, put_cache, upsert_place

log = get_logger("worker.job")
MAX_ERRORS_KEPT = 20


class Progress:
    """Menjaga dict progres dan menuliskannya ke DB (dibatasi ~1x/detik)."""

    def __init__(self, job_id: uuid.UUID, total_queries: int):
        self.job_id = job_id
        self.data: dict = {
            "total_queries": total_queries, "done_queries": 0, "cached_queries": 0,
            "failed_queries": 0, "current_query": None, "phase": "queued",
            "found": 0, "query_found": 0, "new": 0, "updated": 0, "truncated": False, "errors": [],
        }
        self._last = 0.0

    def _write(self) -> None:
        with SessionLocal() as db:
            db.execute(update(ScrapeJob).where(ScrapeJob.id == self.job_id).values(progress=self.data))
            db.commit()

    async def flush(self, force: bool = False) -> None:
        if force or time.monotonic() - self._last >= 1.0:
            self._last = time.monotonic()
            await asyncio.to_thread(self._write)

    async def set(self, force: bool = False, **kw) -> None:
        self.data.update(kw)
        await self.flush(force)

    def add_error(self, query: str, message: str) -> None:
        errs = self.data["errors"]
        if len(errs) < MAX_ERRORS_KEPT:
            errs.append({"query": query, "error": message})


def _set_status(job_id, status: str, error: str | None = None, finished: bool = False) -> None:
    vals: dict = {"status": status, "error": error}
    if finished:
        vals["finished_at"] = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(**vals))
        db.commit()


def _cancel_requested(job_id) -> bool:
    with SessionLocal() as db:
        return bool(db.scalar(select(ScrapeJob.cancel_requested).where(ScrapeJob.id == job_id)))


def _load(job_id) -> tuple[str, dict] | None:
    with SessionLocal() as db:
        job = db.get(ScrapeJob, job_id)
        return (job.status, dict(job.params)) if job else None


def _prepare(params: dict, max_queries: int):
    with SessionLocal() as db:
        plan, _ = planner.plan_for_params(db, params, max_queries)
        chain = planner.load_chain(db, params["region_kode"])
        matcher = planner.build_matcher(db, chain)
    return plan, matcher


def _use_cache(job_id, query: str, detail: bool, wanted: int, ttl: int, budget: int) -> list[int] | None:
    with SessionLocal() as db:
        ids = get_cached(db, query, detail, wanted, ttl)
        if ids is None:
            return None
        ids = ids[:budget]
        link_places(db, job_id, ids)
        db.commit()
        return ids


def _save_places(job_id, pq, places, matcher, cache: tuple[bool, int, bool] | None = None):
    """Upsert hasil satu query + link ke job. `cache` = (detail, batas, lengkap?) bila cache perlu
    disimpan (hanya pada penyimpanan akhir). Return (ids, jumlah_baru)."""
    ids: list[int] = []
    new = 0
    with SessionLocal() as db:
        for p in places:
            in_region, kec_kode = matcher.evaluate(p.alamat)
            region_kode = kec_kode or pq.region_kode
            pid, inserted = upsert_place(db, p, region_kode, in_region)
            ids.append(pid)
            new += inserted
        link_places(db, job_id, ids)
        if cache is not None:
            put_cache(db, pq.query, cache[0], cache[1], cache[2], ids)
        db.commit()
    return ids, new


async def run_scrape_job(job_id: str, stop: asyncio.Event | None = None) -> str:
    """Jalankan job. `stop` (opsional) = sinyal berhenti dari proses worker (aplikasi ditutup):
    job diakhiri sebagai 'cancelled' dengan hasil sebagian tetap tersimpan."""
    settings = get_settings()
    jid = uuid.UUID(job_id)

    loaded = await asyncio.to_thread(_load, jid)
    if loaded is None:
        log.warning("job_missing", job_id=job_id)
        return "missing"
    status, params = loaded
    if status != "queued":  # mis. dibatalkan saat masih antre
        log.info("job_skipped", job_id=job_id, status=status)
        return status

    max_results = int(params.get("max_results") or settings.scrape_max_results_default)
    detail = bool(params.get("detail"))
    force = bool(params.get("force_refresh"))
    structlog_ctx = {"job_id": job_id}
    log.info("job_start", **structlog_ctx, params=params)

    try:
        plan, matcher = await asyncio.to_thread(_prepare, params, settings.scrape_max_queries)
    except planner.PlanError as exc:
        await asyncio.to_thread(_set_status, jid, "failed", str(exc), True)
        return "failed"

    progress = Progress(jid, len(plan))
    await asyncio.to_thread(_set_status, jid, "running")
    await progress.set(force=True, phase="starting")

    shutting_down = False

    async def is_cancelled() -> bool:
        nonlocal shutting_down
        if stop is not None and stop.is_set():
            shutting_down = True
            return True
        return await asyncio.to_thread(_cancel_requested, jid)

    found_ids: set[int] = set()
    final = "done"
    error: str | None = None

    async def on_scraper_progress(info: dict) -> None:
        await progress.set(
            phase=info.get("phase", progress.data["phase"]),
            current_query=info.get("query", progress.data["current_query"]),
            query_found=info.get("found", 0),
        )

    try:
        async with AsyncExitStack() as stack:
            scraper: MapsScraper | None = None
            for pq in plan:
                if await is_cancelled():
                    raise JobCancelled("dibatalkan oleh user")
                remaining = max_results - len(found_ids)
                if remaining <= 0:
                    progress.data["truncated"] = True
                    break
                await progress.set(current_query=pq.query, phase="checking_cache")

                ids = None
                if not force:
                    ids = await asyncio.to_thread(
                        _use_cache, jid, pq.query, detail, remaining, settings.scrape_cache_days, remaining
                    )
                if ids is not None:
                    progress.data["cached_queries"] += 1
                    log.info("query_cache_hit", **structlog_ctx, query=pq.query, places=len(ids))
                else:
                    if scraper is None:  # browser baru dibuka saat benar-benar perlu
                        cfg = ScrapeConfig.from_settings(max_results=remaining, detail=detail)
                        scraper = await stack.enter_async_context(
                            MapsScraper(cfg, on_progress=on_scraper_progress, should_cancel=is_cancelled)
                        )
                    scraper.cfg.max_results = remaining
                    partial: set[int] = set()

                    async def on_list(found_places, pq=pq):
                        # simpan hasil awal segera (sebelum mode detail) agar UI bisa menampilkannya
                        ids_, new_ = await asyncio.to_thread(_save_places, jid, pq, found_places, matcher)
                        partial.update(ids_)
                        found_ids.update(ids_)
                        progress.data["new"] += new_
                        progress.data["updated"] += len(ids_) - new_
                        progress.data["found"] = len(found_ids)
                        await progress.flush(force=True)

                    try:
                        places = await scraper.search(pq.query, on_list=on_list)
                    except BlockedError:
                        raise
                    except JobCancelled:
                        raise
                    except ScrapeError as exc:
                        # hasil awal (bila ada) tetap tersimpan
                        progress.data["failed_queries"] += 1
                        progress.data["done_queries"] += 1
                        progress.add_error(pq.query, str(exc))
                        log.error("query_failed", **structlog_ctx, query=pq.query, error=str(exc))
                        await progress.flush(force=True)
                        await scraper.pause()
                        continue
                    complete = len(places) < remaining
                    ids, new = await asyncio.to_thread(
                        _save_places, jid, pq, places, matcher, (detail, remaining, complete)
                    )
                    extra = [i for i in ids if i not in partial]
                    progress.data["new"] += new
                    progress.data["updated"] += len(extra) - new
                    await scraper.pause()

                found_ids.update(ids)
                progress.data["done_queries"] += 1
                progress.data["found"] = len(found_ids)
                await progress.flush(force=True)

        if progress.data["total_queries"] and progress.data["failed_queries"] == progress.data["total_queries"]:
            final, error = "failed", "semua query gagal; lihat progress.errors dan screenshot di folder debug"
    except BlockedError as exc:
        final, error = "blocked", str(exc)
    except JobCancelled:
        final = "cancelled"
        error = "Aplikasi ditutup saat pencarian berjalan; hasil yang sudah terkumpul tetap tersimpan." if shutting_down else None
    except Exception as exc:  # noqa: BLE001 - job tidak boleh meninggalkan status 'running'
        log.exception("job_crashed", **structlog_ctx)
        final, error = "failed", f"{type(exc).__name__}: {exc}"

    progress.data.update(phase=final, current_query=None, found=len(found_ids))
    await asyncio.to_thread(progress._write)
    await asyncio.to_thread(_set_status, jid, final, error, True)
    log.info("job_finished", **structlog_ctx, status=final, found=len(found_ids), error=error)
    return final


def mark_orphaned_running_jobs() -> int:
    """Dipanggil saat worker start: job 'running' sisa crash/restart ditandai gagal."""
    with SessionLocal() as db:
        ids = db.scalars(select(ScrapeJob.id).where(ScrapeJob.status == "running")).all()
        for jid in ids:
            db.execute(
                update(ScrapeJob).where(ScrapeJob.id == jid).values(
                    status="failed", error="worker berhenti saat job berjalan", finished_at=datetime.now(timezone.utc)
                )
            )
        db.commit()
        return len(ids)
