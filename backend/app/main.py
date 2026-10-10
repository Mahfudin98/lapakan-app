import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import categories, jobs, places, regions
from app.config import get_settings
from app.db import engine
from app.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(title="Peta Toko API")
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
    return {"status": "ok", "app": "peta-toko", "postgis": postgis}


# Edisi desktop: API dan antarmuka dilayani dari satu alamat (tanpa CORS). Dipasang paling akhir
# supaya rute API di atas diprioritaskan.
_static = os.environ.get("PETATOKO_STATIC_DIR")
if _static and Path(_static).is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="web")
