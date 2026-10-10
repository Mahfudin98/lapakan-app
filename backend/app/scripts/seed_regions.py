"""Impor wilayah Kemendagri dari emsifa/api-wilayah-indonesia (static JSON).

    python -m app.scripts.seed_regions [--max-level 4] [--concurrency 16]

Respons di-cache ke /data/wilayah_cache sehingga bisa di-resume dan di-rerun tanpa
mengunduh ulang. Idempotent (upsert).
"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.logging import get_logger, setup_logging
from app.models import Region

BASE_URL = "https://emsifa.github.io/api-wilayah-indonesia/api"
CACHE_DIR = Path("/data/wilayah_cache")
BATCH = 5000

log = get_logger("seed_regions")


async def fetch(client: httpx.AsyncClient, sem: asyncio.Semaphore, path: str) -> list[dict]:
    cache_file = CACHE_DIR / path.replace("/", "__")
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    async with sem:
        for attempt in range(1, 6):
            try:
                resp = await client.get(f"{BASE_URL}/{path}")
                resp.raise_for_status()
                data = resp.json()
                cache_file.write_text(json.dumps(data), encoding="utf-8")
                return data
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("fetch_retry", path=path, attempt=attempt, error=str(exc))
                await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"gagal mengunduh {path}")


async def collect(max_level: int, concurrency: int) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        provinces = await fetch(client, sem, "provinces.json")
        rows += [{"kode": p["id"], "nama": p["name"], "level": 1, "parent_kode": None} for p in provinces]
        log.info("level_done", level=1, count=len(provinces))

        parents = [p["id"] for p in provinces]
        for level, endpoint in ((2, "regencies"), (3, "districts"), (4, "villages")):
            if level > max_level:
                break
            results = await asyncio.gather(
                *(fetch(client, sem, f"{endpoint}/{pid}.json") for pid in parents)
            )
            level_rows = [
                {"kode": item["id"], "nama": item["name"], "level": level, "parent_kode": pid}
                for pid, items in zip(parents, results)
                for item in items
            ]
            rows += level_rows
            parents = [r["kode"] for r in level_rows]
            log.info("level_done", level=level, count=len(level_rows))
    return rows


def save(rows: list[dict]) -> None:
    # sumber memuat beberapa kode ganda; upsert tidak boleh menyentuh baris yang sama dua kali per statement
    unique = {r["kode"]: r for r in rows}
    if len(unique) != len(rows):
        log.warning("duplicate_kode_dropped", count=len(rows) - len(unique))
    rows = list(unique.values())
    with SessionLocal() as db:
        # urut per level supaya FK parent sudah ada
        rows.sort(key=lambda r: r["level"])
        for i in range(0, len(rows), BATCH):
            stmt = insert(Region).values(rows[i : i + BATCH])
            stmt = stmt.on_conflict_do_update(
                index_elements=["kode"],
                set_={"nama": stmt.excluded.nama, "level": stmt.excluded.level,
                      "parent_kode": stmt.excluded.parent_kode},
            )
            db.execute(stmt)
        db.commit()
    log.info("regions_saved", total=len(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-level", type=int, default=4, choices=[1, 2, 3, 4])
    parser.add_argument("--concurrency", type=int, default=16)
    args = parser.parse_args()
    setup_logging()
    rows = asyncio.run(collect(args.max_level, args.concurrency))
    save(rows)


if __name__ == "__main__":
    main()
