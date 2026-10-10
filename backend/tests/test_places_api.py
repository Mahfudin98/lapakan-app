"""Tes integrasi /places (butuh Postgres+PostGIS; skip otomatis bila tidak tersedia)."""
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import delete, update

from app.db import SessionLocal
from app.main import app
from app.models import Place, Region
from app.scraper.parser import PlaceData
from app.services.places import upsert_place

TAG = "pt" + uuid.uuid4().hex[:8]
ANDIR = "3273180"


def _db_ready() -> bool:
    try:
        with SessionLocal() as db:
            return db.get(Region, ANDIR) is not None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="DB/wilayah seed tidak tersedia")

client = TestClient(app)  # tanpa lifespan: tidak butuh Redis

# huruf = nama; koordinat membesar jaraknya dari titik acuan A
SPEC = {
    "A": dict(rating=5.0, review_count=2, lat=-6.9000, lng=107.6000, telepon="021-1", kat="Salon", ir=True),
    "B": dict(rating=4.8, review_count=900, lat=-6.9100, lng=107.6000, website="https://b.id", kat="Salon", ir=None),
    "C": dict(rating=4.0, review_count=100, lat=-6.9500, lng=107.6000, kat="Spa", ir=False),
    "D": dict(rating=4.5, review_count=None, lat=-6.9050, lng=107.6000, kat="Spa", ir=None, status="closed_permanently"),
    "E": dict(rating=None, review_count=0, lat=None, lng=None, kat=None, ir=None),
}
ID: dict[str, int] = {}


@pytest.fixture(scope="module", autouse=True)
def data():
    with SessionLocal() as db:
        for k, s in SPEC.items():
            pid, _ = upsert_place(
                db,
                PlaceData(
                    google_place_key=f"{TAG}-{k}", nama=f"{TAG} {k}", rating=s["rating"],
                    review_count=s["review_count"], lat=s["lat"], lng=s["lng"], telepon=s.get("telepon"),
                    website=s.get("website"), kategori_google=s["kat"],
                    status_bisnis=s.get("status", "operational"),
                ),
                ANDIR, s["ir"],
            )
            ID[k] = pid
        # waktu scrape berbeda: C paling baru, lalu A, B, D, E
        now = datetime.now(timezone.utc)
        for i, k in enumerate("CABDE"):
            db.execute(update(Place).where(Place.id == ID[k]).values(last_scraped_at=now - timedelta(hours=i)))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(Place).where(Place.google_place_key.like(f"{TAG}%")))
        db.commit()


def get(path="", **params):
    params.setdefault("q", TAG)
    r = client.get(f"/places{path}", params=params)
    assert r.status_code == 200, r.text
    return r


def order(**params) -> str:
    inv = {v: k for k, v in ID.items()}
    return "".join(inv[i["id"]] for i in get(page_size=200, **params).json()["items"])


# --- pengurutan ---------------------------------------------------------------------------------
def test_sort_skor_bayesian_prefers_many_reviews_and_puts_unknown_last():
    # 5.0 dari 2 ulasan (A) tidak boleh mengalahkan 4.8 dari 900 ulasan (B); D/E tanpa data ulasan di bawah
    assert order(sort="skor") == "BACDE"


def test_skor_values_use_average_rating_of_results():
    body = get(sort="skor", page_size=200).json()
    c = body["meta"]["avg_rating"]
    assert c == pytest.approx((5.0 + 4.8 + 4.0 + 4.5) / 4, abs=1e-3)
    by_id = {i["id"]: i for i in body["items"]}
    expected_b = (900 / 920) * 4.8 + (20 / 920) * c
    assert by_id[ID["B"]]["score"] == pytest.approx(expected_b, abs=1e-6)
    assert by_id[ID["D"]]["score"] is None


def test_average_rating_c_follows_the_filtered_result_set():
    # C = rata-rata seluruh hasil yang sedang tampil; filter mengubahnya (A,B saja -> 4,9)
    b = get(sort="skor", min_rating=4.6).json()
    assert b["meta"]["avg_rating"] == pytest.approx(4.9, abs=1e-3)
    assert order(sort="skor", min_rating=4.6) == "AB"


def test_m_parameter_changes_score():
    lo = {i["id"]: i["score"] for i in get(sort="skor", m=0).json()["items"]}
    assert lo[ID["A"]] == pytest.approx(5.0)  # m=0 -> rating mentah
    assert order(sort="skor", m=0) == "ABCDE"


def test_sort_terpopuler():
    assert order(sort="terpopuler") == "BCAED"


def test_sort_rating():
    assert order(sort="rating") == "ABDCE"


def test_sort_nama_and_terbaru():
    assert order(sort="nama") == "ABCDE"
    assert order(sort="terbaru") == "CABDE"


def test_sort_terdekat_uses_postgis_distance_in_km():
    body = get(sort="terdekat", lat=-6.9000, lng=107.6000, page_size=200).json()
    assert order(sort="terdekat", lat=-6.9000, lng=107.6000) == "ADBCE"  # E tanpa geom di akhir
    d = {i["id"]: i["distance_km"] for i in body["items"]}
    assert d[ID["A"]] == pytest.approx(0, abs=0.001)
    assert d[ID["B"]] == pytest.approx(1.11, abs=0.02)  # 0,01 derajat lintang ~ 1,11 km
    assert d[ID["C"]] == pytest.approx(5.56, abs=0.05)
    assert d[ID["E"]] is None


def test_terdekat_requires_reference_point():
    r = client.get("/places", params={"q": TAG, "sort": "terdekat"})
    assert r.status_code == 422


def test_distance_shown_for_any_sort_when_reference_given():
    items = get(sort="rating", lat=-6.9, lng=107.6).json()["items"]
    assert all(i["distance_km"] is not None for i in items if i["lat"] is not None)


# --- filter -----------------------------------------------------------------------------------------
def test_filters():
    assert order(sort="nama", min_rating=4.6) == "AB"
    assert order(sort="nama", min_reviews=100) == "BC"
    assert order(sort="nama", has_phone=True) == "A"
    assert order(sort="nama", has_website=True) == "B"
    assert order(sort="nama", hide_closed=True) == "ABCE"
    assert order(sort="nama", kategori=["Salon"]) == "AB"
    assert order(sort="nama", kategori=["Salon", "Spa"]) == "ABCD"


def test_region_filters():
    assert order(sort="nama", region_filter="hide_outside") == "ABDE"  # unknown (None) tetap tampil
    assert order(sort="nama", region_filter="inside_only") == "A"
    assert order(sort="nama", region_kode=ANDIR) == "ABCDE"
    assert order(sort="nama", region_kode="3273") == "ABCDE"  # induk mencakup anak
    assert order(sort="nama", region_kode="3273181") == ""


def test_region_kode_must_be_digits():
    assert client.get("/places", params={"region_kode": "32%"}).status_code == 422


def test_search_q_escapes_wildcards():
    assert get(q="%").json()["total"] == 0 or "%" in str(get(q="%").json()["items"])


# --- pagination ----------------------------------------------------------------------------------------
def test_pagination_is_stable_and_complete():
    seen = []
    for page in (1, 2, 3):
        b = get(sort="rating", page=page, page_size=2).json()
        assert b["total"] == 5 and b["pages"] == 3
        seen += [i["id"] for i in b["items"]]
    assert len(seen) == 5 and len(set(seen)) == 5
    assert get(sort="rating", page=4, page_size=2).json()["items"] == []


def test_page_size_limit():
    assert client.get("/places", params={"page_size": 500}).status_code == 422


def test_meta_with_reviews_counts_known_review_counts():
    assert get().json()["meta"]["with_reviews"] == 4  # D tidak punya data jumlah ulasan


# --- peta / facet / detail --------------------------------------------------------------------------------
def test_map_points_exclude_places_without_geometry():
    b = get("/map").json()
    assert b["total"] == 4 and len(b["points"]) == 4 and b["truncated"] is False
    assert {p["nama"] for p in b["points"]} == {f"{TAG} {k}" for k in "ABCD"}


def test_facets_ignore_kategori_filter_but_apply_others():
    f = {x["kategori"]: x["count"] for x in get("/facets").json()}
    assert f == {"Salon": 2, "Spa": 2}
    f2 = {x["kategori"]: x["count"] for x in get("/facets", min_rating=4.6).json()}
    assert f2 == {"Salon": 2}


def test_get_place_detail_and_404():
    r = client.get(f"/places/{ID['B']}")
    assert r.status_code == 200 and r.json()["nama"] == f"{TAG} B" and r.json()["lat"] == pytest.approx(-6.91)
    assert client.get("/places/999999999").status_code == 404


# --- ekspor ------------------------------------------------------------------------------------------------------
def test_export_csv_respects_filters_and_order():
    r = client.get("/places/export", params={"q": TAG, "sort": "skor", "min_reviews": 2, "format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and r.headers["content-disposition"].endswith('.csv"')
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM UTF-8
    lines = r.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("Nama,Kategori,Rating")
    assert [ln.split(",")[0] for ln in lines[1:]] == [f"{TAG} B", f"{TAG} A", f"{TAG} C"]


def test_export_xlsx_is_valid_workbook():
    r = client.get("/places/export", params={"q": TAG, "sort": "nama", "format": "xlsx"})
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][0] == "Nama" and len(rows) == 6
    assert rows[1][0] == f"{TAG} A" and rows[1][2] == 5.0


def test_export_neutralises_formula_injection():
    with SessionLocal() as db:
        upsert_place(db, PlaceData(google_place_key=f"{TAG}-inj", nama="=HYPERLINK(\"http://x\")", rating=4.0,
                                   alamat="@evil"), ANDIR, None)
        db.commit()
    r = client.get("/places/export", params={"region_kode": ANDIR, "q": "HYPERLINK", "format": "csv"})
    body = r.text.lstrip("﻿")
    assert "'=HYPERLINK" in body and "'@evil" in body
    assert "\n=HYPERLINK" not in body


def test_export_invalid_format():
    assert client.get("/places/export", params={"format": "pdf"}).status_code == 422


def test_meta_outside_count_ignores_region_filter_but_keeps_others():
    # C berstatus in_region=False; hide_outside menyembunyikannya, outside_count tetap melaporkan 1
    body = get(region_filter="hide_outside").json()
    assert body["total"] == 4 and body["meta"]["outside_count"] == 1
    assert get(region_filter="all").json()["meta"]["outside_count"] == 1
    assert get(min_rating=4.6).json()["meta"]["outside_count"] == 0  # C (4.0) tersaring oleh filter lain
