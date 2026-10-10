from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://petatoko:petatoko@localhost:5432/petatoko"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    scrape_max_results_default: int = 200
    scrape_delay_min: float = 2.0
    scrape_delay_max: float = 5.0
    scrape_cache_days: int = 7
    scrape_max_queries: int = 300
    worker_job_timeout: int = 6 * 3600
    bayesian_m: int = 20
    debug_dir: str = "/data/debug"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
