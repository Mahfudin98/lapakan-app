from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import categories, jobs, places, regions
from app.config import get_settings
from app.db import engine
from app.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq.aclose()


app = FastAPI(title="Peta Toko API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(regions.router)
app.include_router(categories.router)
app.include_router(jobs.router)
app.include_router(places.router)


@app.get("/health", tags=["meta"])
def health():
    with engine.connect() as conn:
        postgis = conn.execute(text("SELECT postgis_version()")).scalar()
    return {"status": "ok", "postgis": postgis}
