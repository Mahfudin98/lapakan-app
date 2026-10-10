"""Worker: mengambil job 'queued' dari database dan menjalankannya satu per satu (1 browser).

    python -m app.workers.runner

Tidak butuh Redis: antrean = tabel scrape_jobs. Satu worker saja yang boleh aktif; dijaga dengan
advisory lock PostgreSQL sehingga menjalankan dua worker tidak akan membuat dua browser.
"""
import asyncio
import os
import signal
import sys
from pathlib import Path

from sqlalchemy import select, text

from app.config import get_settings
from app.db import SessionLocal, engine
from app.logging import get_logger, setup_logging
from app.models import ScrapeJob
from app.workers.tasks import mark_orphaned_running_jobs, run_scrape_job

log = get_logger("worker")
LOCK_KEY = 7351001  # kunci advisory unik untuk worker Peta Toko
POLL_SECONDS = 1.5


def next_queued_job_id() -> str | None:
    with SessionLocal() as db:
        jid = db.scalar(
            select(ScrapeJob.id).where(ScrapeJob.status == "queued").order_by(ScrapeJob.created_at).limit(1)
        )
        return str(jid) if jid else None


async def main() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK: Windows (CTRL_BREAK_EVENT dari peluncur)
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows: asyncio tidak mendukung add_signal_handler
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))

    # Windows (edisi desktop): peluncur tidak dapat mengirim sinyal ke proses tanpa konsol, jadi permintaan
    # berhenti disampaikan lewat berkas.
    stop_file = os.environ.get("PETATOKO_STOP_FILE")
    watcher = None
    if stop_file:
        async def watch_stop_file():
            while not stop.is_set():
                if Path(stop_file).exists():
                    log.info("stop_file_detected")
                    stop.set()
                    return
                await asyncio.sleep(1)

        watcher = asyncio.create_task(watch_stop_file())

    # koneksi khusus yang memegang lock selama worker hidup
    lock_conn = engine.connect()
    got = lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
    if not got:
        log.error("worker_already_running")
        lock_conn.close()
        return 1

    n = await asyncio.to_thread(mark_orphaned_running_jobs)
    log.info("worker_started", orphaned_jobs_marked_failed=n)
    try:
        while not stop.is_set():
            job_id = await asyncio.to_thread(next_queued_job_id)
            if job_id is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                continue
            status = await run_scrape_job(job_id, stop)
            log.info("job_done", job_id=job_id, status=status)
    finally:
        if watcher:
            watcher.cancel()
        lock_conn.close()
    log.info("worker_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
