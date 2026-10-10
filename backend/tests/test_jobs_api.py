"""Tes API /jobs (butuh PostgreSQL; di-skip bila tidak tersedia)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

from app.db import SessionLocal
from app.main import app
from app.models import Region, ScrapeJob

ANDIR = "3273180"
TAG = "ja" + uuid.uuid4().hex[:8]


def _db_ready() -> bool:
    try:
        with SessionLocal() as db:
            return db.get(Region, ANDIR) is not None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="DB tidak tersedia")
client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with SessionLocal() as db:
        db.execute(delete(ScrapeJob).where(ScrapeJob.params["keywords"].astext.like(f"%{TAG}%")))
        db.commit()


def create(**over):
    body = {"region_kode": ANDIR, "keywords": [TAG], "max_results": 5, **over}
    return client.post("/jobs", json=body)


def set_status(job_id: str, status: str):
    with SessionLocal() as db:
        db.execute(text("update scrape_jobs set status = :s where id = :i"), {"s": status, "i": job_id})
        db.commit()


def test_create_job_is_queued_without_any_broker():
    r = create()
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "queued" and body["progress"]["total_queries"] == 1
    assert client.get(f"/jobs/{body['id']}").json()["id"] == body["id"]


def test_create_job_validation():
    assert client.post("/jobs", json={"region_kode": ANDIR}).status_code == 422  # tanpa kategori/kata kunci
    assert create(region_kode="9999999").status_code == 422  # wilayah tidak ada
    assert create(max_results=0).status_code == 422


def test_preview_does_not_create_job():
    with SessionLocal() as db:
        before = db.scalar(text("select count(*) from scrape_jobs"))
    r = client.post("/jobs/preview", json={"region_kode": ANDIR, "keywords": [TAG]})
    assert r.status_code == 200 and r.json()["total_queries"] == 1
    with SessionLocal() as db:
        assert db.scalar(text("select count(*) from scrape_jobs")) == before


def test_cancel_queued_job_cancels_immediately():
    jid = create().json()["id"]
    r = client.post(f"/jobs/{jid}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled" and r.json()["finished_at"] is not None


def test_cancel_running_job_only_sets_flag_for_the_worker():
    jid = create().json()["id"]
    set_status(jid, "running")
    r = client.post(f"/jobs/{jid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "running"  # worker yang menghentikannya
    with SessionLocal() as db:
        assert db.scalar(text("select cancel_requested from scrape_jobs where id = :i"), {"i": jid}) is True


@pytest.mark.parametrize("final", ["done", "failed", "blocked", "cancelled"])
def test_cancel_finished_job_is_rejected(final):
    jid = create().json()["id"]
    set_status(jid, final)
    assert client.post(f"/jobs/{jid}/cancel").status_code == 409


def test_unknown_job_is_404():
    assert client.get(f"/jobs/{uuid.uuid4()}").status_code == 404
    assert client.post(f"/jobs/{uuid.uuid4()}/cancel").status_code == 404
