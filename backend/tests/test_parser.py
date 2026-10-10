from pathlib import Path

import pytest

from app.scraper import parser

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


# --- parse_place_url ---------------------------------------------------------------------
def test_parse_place_url_extracts_fid_and_exact_coords():
    url = (
        "https://www.google.com/maps/place/TOKO+MAHMUD+COSMETIC/data=!4m7!3m6"
        "!1s0x2e68ef1c7605932d:0xa3e0da284260923a!8m2!3d-6.9027974!4d107.5959117"
        "!16s%2Fg%2F11b6dgh1k0?authuser=0&hl=id"
    )
    info = parser.parse_place_url(url)
    assert info.key == "0x2e68ef1c7605932d:0xa3e0da284260923a"
    assert info.lat == pytest.approx(-6.9027974)
    assert info.lng == pytest.approx(107.5959117)


def test_parse_place_url_falls_back_to_viewport_center():
    info = parser.parse_place_url("https://www.google.com/maps/place/X/@-6.91,107.59,17z/data=!1s0xaa:0xbb")
    assert info.key == "0xaa:0xbb"
    assert (info.lat, info.lng) == (-6.91, 107.59)


def test_parse_place_url_without_data():
    info = parser.parse_place_url("https://www.google.com/maps")
    assert info.key is None and info.lat is None


# --- angka -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [("1.234", 1234), ("1,234", 1234), ("87", 87), ("1,2 rb", 1200), ("3K", 3000), ("abc", None)],
)
def test_parse_count(text, expected):
    assert parser.parse_count(text) == expected


# --- feed ------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def feed():
    return parser.parse_feed(load("search_results_id.html"))


def test_feed_parses_all_cards(feed):
    assert len(feed.places) == 7
    assert all(p.google_place_key.startswith("0x") for p in feed.places)


def test_feed_first_card_fields(feed):
    p = feed.places[0]
    assert p.nama == "TOKO MAHMUD COSMETIC"
    assert p.google_place_key == "0x2e68ef1c7605932d:0xa3e0da284260923a"
    assert p.rating == 4.5
    assert p.kategori_google == "Toko Kosmetik"
    assert p.alamat == "Jalan Mahmud No.8 Pasir Kaliki"
    assert p.telepon == "(022) 6032097"
    assert p.lat == pytest.approx(-6.9027974)
    assert p.lng == pytest.approx(107.5959117)
    assert p.status_bisnis == parser.OPERATIONAL
    assert "Tutup pukul 17.00" in p.jam_buka["ringkasan"]


def test_feed_card_without_phone(feed):
    p = next(x for x in feed.places if x.nama == "Toko Jelita Kosmetik")
    assert p.telepon is None
    assert p.rating is None
    assert p.review_count == 0  # "Tidak ada ulasan"
    assert p.alamat == "Pasar andir trade center, Lt dasar blok g no"


def test_feed_phone_without_parentheses(feed):
    p = next(x for x in feed.places if x.nama == "Gaya Beauty Utama")
    assert p.telepon == "0877-7353-5888"
    assert p.rating == 5.0
    assert p.alamat == "No.11 B, Jl. Ence Azis"


def test_feed_review_count_is_none_in_limited_view(feed):
    # tampilan terbatas Google (tanpa login) tidak menampilkan jumlah ulasan
    p = next(x for x in feed.places if x.nama == "Elsa Cosmetics")
    assert p.rating == 4.6 and p.review_count is None


def test_feed_end_of_list_not_reached_in_partial_page(feed):
    assert feed.end_of_list is False


def test_scrolled_feed_dedupes_places():
    res = parser.parse_feed(load("search_results_scrolled_id.html"))
    keys = [p.google_place_key for p in res.places]
    assert len(keys) == len(set(keys))
    assert res.card_count > len(keys)  # fixture berisi duplikat (Belleza Beauty Shop)
    assert len(keys) >= 50


def test_end_of_list_marker_detected():
    html = (
        '<div role="feed"><div role="article"><a aria-label="A" '
        'href="https://www.google.com/maps/place/A/data=!1s0x1:0x2!3d-6.1!4d107.1"></a></div>'
        "<p>Anda telah mencapai akhir daftar.</p></div>"
    )
    assert parser.parse_feed(html).end_of_list is True


def test_feed_missing_returns_empty():
    assert parser.parse_feed("<html><body>kosong</body></html>").places == []


def test_card_with_review_count_in_aria_label():
    html = (
        '<div role="feed"><div role="article"><a aria-label="Salon X" '
        'href="https://www.google.com/maps/place/X/data=!1s0x1:0x2!3d-6.1!4d107.1"></a>'
        '<span role="img" aria-label="4,8 bintang 1.234 Ulasan"></span>'
        "<div><span>Salon</span><span>· Jl. Mawar 1</span></div></div></div>"
    )
    p = parser.parse_feed(html).places[0]
    assert (p.rating, p.review_count, p.kategori_google, p.alamat) == (4.8, 1234, "Salon", "Jl. Mawar 1")


def test_card_with_review_count_in_parentheses():
    html = (
        '<div role="feed"><div role="article"><a aria-label="Salon X" '
        'href="https://www.google.com/maps/place/X/data=!1s0x1:0x2!3d-6.1!4d107.1"></a>'
        '<span role="img" aria-label="4,8 bintang"></span><span>4,8</span><span>(1.234)</span>'
        "<span>Salon</span><span>· Jl. Mawar 1</span><span>(021) 555123</span></div></div>"
    )
    p = parser.parse_feed(html).places[0]
    assert p.review_count == 1234
    assert p.telepon == "(021) 555123"  # tidak tertukar dengan jumlah ulasan


def test_permanently_closed_status():
    html = (
        '<div role="feed"><div role="article"><a aria-label="Toko Z" '
        'href="https://www.google.com/maps/place/Z/data=!1s0x1:0x2!3d-6.1!4d107.1"></a>'
        "<span>Toko</span><span>Tutup permanen</span></div></div>"
    )
    assert parser.parse_feed(html).places[0].status_bisnis == parser.CLOSED_PERMANENTLY


# --- detail -------------------------------------------------------------------------------------------
DETAIL_URL = (
    "https://www.google.com/maps/place/Toko+Rama+Sinta/@-6.9,107.6,14z/data=!4m10!3m6"
    "!1s0x2e68e7b0e0e0e0e0:0x1234567890abcdef!8m2!3d-6.9137!4d107.6014"
)


def test_detail_fields():
    d = parser.parse_detail(load("place_detail_id.html"), DETAIL_URL)
    assert d is not None
    assert d.nama == "Toko Rama Sinta"
    assert d.alamat.startswith("Jl. Astina No.23")
    assert d.telepon == "(022) 6018433"
    assert d.kategori_google == "Toko Kosmetik"
    assert d.rating == 4.5
    assert d.website is None  # toko ini tidak punya website
    assert d.google_place_key == "0x2e68e7b0e0e0e0e0:0x1234567890abcdef"
    assert d.lat == pytest.approx(-6.9137)
    assert d.jam_buka == {"jadwal": {"Sabtu": "09.00–17.00"}}


def test_detail_without_root_returns_none():
    assert parser.parse_detail("<html></html>") is None


def test_merge_detail_overrides_and_keeps_card_data():
    base = parser.PlaceData(google_place_key="k", nama="A", alamat="pendek", jam_buka={"ringkasan": "Buka"})
    det = parser.PlaceData(
        google_place_key="k", nama="A", alamat="alamat lengkap", website="https://a.id",
        review_count=10, jam_buka={"jadwal": {"Senin": "09.00–17.00"}},
    )
    m = parser.merge_detail(base, det)
    assert m.alamat == "alamat lengkap" and m.website == "https://a.id" and m.review_count == 10
    assert m.jam_buka == {"ringkasan": "Buka", "jadwal": {"Senin": "09.00–17.00"}}


# --- deteksi blokir -----------------------------------------------------------------------------------------
def test_detect_block_by_url():
    assert parser.detect_block("https://www.google.com/sorry/index?continue=x", "<html></html>")


def test_detect_block_by_text():
    html = "<html><body><p>Our systems have detected unusual traffic from your network.</p></body></html>"
    assert parser.detect_block("https://www.google.com/maps/search/x", html)


def test_detect_block_by_captcha_element():
    assert parser.detect_block("https://x", '<form id="captcha-form"></form>')


def test_no_block_on_normal_results():
    assert parser.detect_block("https://www.google.com/maps/search/x", load("search_results_id.html")) is None


def test_no_block_when_shop_name_mentions_robot():
    html = '<div role="feed"><div role="article">Toko Bukan Robot unusual traffic</div></div>'
    assert parser.detect_block("https://www.google.com/maps/search/x", html) is None


def test_no_results_pattern_matches_page_text():
    from app.scraper import selectors as sel

    assert any(p.search("Google Maps tidak dapat menemukan zzz") for p in sel.NO_RESULTS_PATTERNS)
    assert any(p.search("Google Maps can't find zzz") for p in sel.NO_RESULTS_PATTERNS)


def test_action_button_text_is_not_taken_as_address():
    html = (
        '<div role="feed"><div role="article"><a aria-label="Klinik X" '
        'href="https://www.google.com/maps/place/X/data=!1s0x1:0x2!3d-6.1!4d107.1"></a>'
        '<span role="img" aria-label="4,3 bintang"></span><span>4,3</span>'
        "<span>Klinik Kecantikan</span><span>· Rute</span><span>18888</span></div></div>"
    )
    p = parser.parse_feed(html).places[0]
    assert p.kategori_google == "Klinik Kecantikan"
    assert p.alamat is None
