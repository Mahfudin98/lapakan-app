"""arq worker:  arq app.workers.worker.WorkerSettings"""
from arq.connections import RedisSettings

from app.config import get_settings
from app.logging import get_logger, setup_logging
from app.workers.tasks import mark_orphaned_running_jobs, run_scrape_job

settings = get_settings()
log = get_logger("worker")


async def startup(ctx: dict) -> None:
    setup_logging(settings.log_level)
    n = mark_orphaned_running_jobs()
    log.info("worker_started", orphaned_jobs_marked_failed=n)


class WorkerSettings:
    functions = [run_scrape_job]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1  # 1 browser concurrent
    job_timeout = settings.worker_job_timeout
    keep_result = 0
    max_tries = 1  # jangan ulang otomatis (hindari memukul Google saat error/blokir)
