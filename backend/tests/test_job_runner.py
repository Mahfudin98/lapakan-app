"""Tes integrasi: butuh Postgres (docker compose up db) dengan wilayah ter-seed. Otomatis skip bila tidak ada."""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, select, text

from app.db import SessionLocal
from app.models import JobPlace, Place, QueryCache, Region, ScrapeJob
from app.scraper.maps import BlockedError, ScrapeError
from app.scraper.parser import PlaceData
from app.services.places import cache_key, get_cached, put_cache, upsert_place
from app.workers import tasks

TAG = "pytest-" + uuid.uuid4().hex[:8]
ANDIR = "3273180"


def _db_ready() -> bool:
    try:
        with SessionLocal() as db:
            return db.get(Region, ANDIR) is not None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="DB/wilayah seed tidak tersedia")


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with SessionLocal() as db:
        db.execute(delete(Place).where(Place.google_place_key.like(f"{TAG}%")))
        db.execute(delete(QueryCache).where(QueryCache.query_key.like(f"%{TAG}%")))
        db.execute(delete(ScrapeJob).where(ScrapeJob.params["keywords"].astext.like(f"%{TAG}%")))
        db.commit()


def pd(i: int, **kw) -> PlaceData:
    base = dict(google_place_key=f"{TAG}-{i}", nama=f"Toko {i}", lat=-6.9, lng=107.6, rating=4.0)
    return PlaceData(**{**base, **kw})


# --- upsert ---------------------------------------------------------------------------
def test_upsert_insert_then_update_keeps_enriched_fields():
    with SessionLocal() as db:
        pid, new = upsert_place(db, pd(1, telepon="021-1", website="https://a.id", jam_buka={"jadwal": {"Sabtu": "9-17"}}), ANDIR, True)
        assert new is True
        # scrape berikutnya (mode daftar) tanpa telepon/website tidak boleh menghapusnya
        pid2, new2 = upsert_place(db, pd(1, rating=4.8, jam_buka={"ringkasan": "Buka"}), ANDIR, None)
        db.commit()
        assert (pid2, new2) == (pid, False)
        p = db.get(Place, pid)
        db.refresh(p)
        assert p.telepon == "021-1" and p.website == "https://a.id"
        assert p.rating == 4.8
        assert p.in_region is True  # unknown (None) tidak menimpa True
        assert p.jam_buka == {"jadwal": {"Sabtu": "9-17"}, "ringkasan": "Buka"}
        n = db.execute(text("select st_y(geom::geometry) from places where id=:i"), {"i": pid}).scalar()
        assert n == pytest.approx(-6.9)


def test_cache_validity_rules():
    q = f"salon {TAG}"
    with SessionLocal() as db:
        put_cache(db, q, detail=False, max_results=10, complete=False, place_ids=[1, 2])
        db.commit()
        assert get_cached(db, q.upper(), False, 10, 7) == [1, 2]  # kunci ternormalisasi
        assert get_cached(db, q, False, 50, 7) is None  # terpotong & diminta lebih banyak
        assert get_cached(db, q, True, 10, 7) is None  # butuh detail, cache tanpa detail
        put_cache(db, q, detail=True, max_results=10, complete=True, place_ids=[1, 2])
        db.commit()
        assert get_cached(db, q, True, 999, 7) == [1, 2]  # daftar lengkap: cukup untuk batas berapa pun
        db.execute(text("update query_cache set scraped_at = now() - interval '8 days' where query_key=:k"), {"k": cache_key(q)})
        db.commit()
        assert get_cached(db, q, False, 10, 7) is None  # kedaluwarsa


# --- runner --------------------------------------------------------------------------------
class FakeRedis:
    async def exists(self, key):
        return 0

    async def delete(self, key):
        return 1


def make_fake_scraper(behaviour):
    class FakeScraper:
        def __init__(self, cfg, **kw):
            self.cfg = cfg
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def search(self, query, on_list=None):
            self.calls.append(query)
            result = behaviour(query, self.cfg.max_results)
            if on_list and result:
                await on_list(result)  # seperti scraper asli: hasil awal dilaporkan sebelum detail
            return result

        async def pause(self):
            return None

    return FakeScraper


def new_job(**params) -> uuid.UUID:
    base = dict(region_kode=ANDIR, keywords=[TAG], max_results=50, detail=False, force_refresh=True, category_ids=[])
    with SessionLocal() as db:
        job = ScrapeJob(params={**base, **params}, status="queued", progress={})
        db.add(job)
        db.commit()
        return job.id


def run(job_id):
    return asyncio.run(tasks.run_scrape_job({"redis": FakeRedis()}, str(job_id)))


def status(job_id):
    with SessionLocal() as db:
        j = db.get(ScrapeJob, job_id)
        return j.status, j.error, j.progress, j.finished_at


def test_job_done_links_places_and_flags_region(monkeypatch):
    def behaviour(q, mx):
        return [pd(1, alamat="Jl. A, Kec. Andir, Kota Bandung"), pd(2, alamat="Jl. B, Kec. Cicendo, Kota Bandung")]

    monkeypatch.setattr(tasks, "MapsScraper", make_fake_scraper(behaviour))
    jid = new_job()
    assert run(jid) == "done"
    st, err, prog, fin = status(jid)
    assert st == "done" and err is None and fin is not None
    assert prog["found"] == 2 and prog["new"] == 2
    with SessionLocal() as db:
        flags = dict(db.execute(select(Place.google_place_key, Place.in_region).where(Place.google_place_key.like(f"{TAG}%"))).all())
        assert flags == {f"{TAG}-1": True, f"{TAG}-2": False}
        assert db.scalar(select(JobPlace.job_id).where(JobPlace.job_id == jid).limit(1)) == jid


def test_job_blocked_stops_and_reports(monkeypatch):
    def behaviour(q, mx):
        raise BlockedError("captcha terdeteksi")

    monkeypatch.setattr(tasks, "MapsScraper", make_fake_scraper(behaviour))
    jid = new_job()
    assert run(jid) == "blocked"
    st, err, prog, fin = status(jid)
    assert st == "blocked" and "captcha" in err and fin is not None


def test_job_all_queries_failed_marks_failed(monkeypatch):
    def behaviour(q, mx):
        raise ScrapeError("selector rusak")

    monkeypatch.setattr(tasks, "MapsScraper", make_fake_scraper(behaviour))
    jid = new_job()
    assert run(jid) == "failed"
    st, err, prog, _ = status(jid)
    assert st == "failed" and prog["failed_queries"] == 1 and prog["errors"][0]["error"] == "selector rusak"


def test_job_budget_truncates_total(monkeypatch):
    def behaviour(q, mx):
        return [pd(i) for i in range(mx)]

    monkeypatch.setattr(tasks, "MapsScraper", make_fake_scraper(behaviour))
    jid = new_job(max_results=3)
    assert run(jid) == "done"
    assert status(jid)[2]["found"] == 3


def test_job_cancelled_before_start_is_skipped():
    jid = new_job()
    with SessionLocal() as db:
        db.execute(text("update scrape_jobs set status='cancelled' where id=:i"), {"i": jid})
        db.commit()
    assert run(jid) == "cancelled"


def test_invalid_region_fails_job():
    jid = new_job(region_kode="9999999")
    assert run(jid) == "failed"
    assert "tidak ditemukan" in status(jid)[1]


def test_upsert_jam_buka_never_becomes_array_from_json_null():
    """Regresi: jam_buka None disimpan sebagai JSON null lalu 'null'||{} menjadi array [null, {...}]."""
    with SessionLocal() as db:
        pid, _ = upsert_place(db, pd(7, jam_buka=None), ANDIR, None)
        for jb in ({"ringkasan": "Buka"}, None, {"jadwal": {"Sabtu": "9-17"}}, None):
            upsert_place(db, pd(7, jam_buka=jb), ANDIR, None)
        db.commit()
        kind, val = db.execute(
            text("select jsonb_typeof(jam_buka), jam_buka from places where id=:i"), {"i": pid}
        ).one()
        assert kind == "object"
        assert val == {"ringkasan": "Buka", "jadwal": {"Sabtu": "9-17"}}
        pid2, _ = upsert_place(db, pd(8, jam_buka=None), ANDIR, None)
        upsert_place(db, pd(8, jam_buka=None), ANDIR, None)
        db.commit()
        assert db.execute(text("select jam_buka is null from places where id=:i"), {"i": pid2}).scalar() is True


def test_partial_results_are_kept_when_query_fails_after_list_stage(monkeypatch):
    """Daftar sudah ter-scrape lalu mode detail gagal: hasil awal tetap tersimpan dan ter-link ke job."""
    sample = [pd(21, alamat="Jl. A, Kec. Andir, Kota Bandung"), pd(22)]

    class FailingAfterList(make_fake_scraper(lambda q, mx: sample)):
        async def search(self, query, on_list=None):
            await on_list(sample)
            raise ScrapeError("detail gagal")

    monkeypatch.setattr(tasks, "MapsScraper", FailingAfterList)
    jid = new_job()
    assert run(jid) == "failed"  # satu-satunya query gagal
    st, err, prog, _ = status(jid)
    assert prog["found"] == 2 and prog["new"] == 2 and prog["failed_queries"] == 1
    with SessionLocal() as db:
        linked = db.scalars(select(JobPlace.place_id).where(JobPlace.job_id == jid)).all()
        assert len(linked) == 2


def test_final_pass_does_not_double_count(monkeypatch):
    def behaviour(q, mx):
        return [pd(31), pd(32), pd(33)]

    monkeypatch.setattr(tasks, "MapsScraper", make_fake_scraper(behaviour))
    jid = new_job()
    assert run(jid) == "done"
    prog = status(jid)[2]
    assert prog["found"] == 3 and prog["new"] == 3 and prog["updated"] == 0
