"""Semua selector & pola teks Google Maps dikumpulkan di sini.

Prinsip: utamakan atribut stabil (role, aria-label, data-item-id, href) daripada
class CSS yang diacak Google. Setiap entri berupa *daftar* kandidat, dicoba berurutan;
`first_match` mencatat log saat kandidat utama gagal dan fallback dipakai.
"""
import re

from bs4 import Tag

from app.logging import get_logger

log = get_logger("scraper.selectors")

# --- Halaman hasil pencarian ---------------------------------------------------
FEED = ['[role="feed"]']
# link tiap hasil (stabil: href berisi /maps/place/)
RESULT_LINK = ['a[href*="/maps/place/"]']
# kartu hasil: role=article; fallback = induk dari link
RESULT_CARD = ['[role="article"]']

# --- Panel detail tempat ---------------------------------------------------------
DETAIL_ROOT = ['[role="main"][aria-label]']
DETAIL_READY = ['[data-item-id="address"]', '[data-item-id^="phone"]', 'button[aria-label*="Tulis ulasan"]']
DETAIL_ADDRESS = ['[data-item-id="address"]']
DETAIL_PHONE = ['[data-item-id^="phone:tel:"]']
DETAIL_WEBSITE = ['a[data-item-id="authority"]']
DETAIL_CATEGORY = ['button[jsaction*="category"]', "button.DkEaL"]
DETAIL_HOURS_TABLE = ["table.eK4R0e", "table"]
# elemen untuk mengembangkan jam buka seminggu (id & en)
DETAIL_HOURS_EXPAND = [
    '[role="button"][aria-expanded="false"]:has([aria-label*="jam buka untuk seminggu"])',
    '[role="button"][aria-expanded="false"]:has([aria-label*="open hours for the week"])',
    '[aria-label*="jam buka untuk seminggu"]',
    '[data-item-id="oh"]',
]

RATING_IMG = ['[role="img"][aria-label]']

# --- Pola teks -------------------------------------------------------------------
RE_RATING_LABEL = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:bintang|stars?)", re.I)
RE_REVIEWS_LABEL = re.compile(r"([\d.,]+)\s*(?:ulasan|reviews?)", re.I)
RE_REVIEWS_PAREN = re.compile(r"^\(([\d.,]+(?:\s?[KkRrBb])?)\)$")
RE_PHONE = re.compile(r"^\+?[\d(][\d\s()\-]{6,}$")
# teks tombol aksi / angka pendek yang bukan bagian dari alamat atau kategori
RE_JUNK_TOKEN = re.compile(r"^(rute|situs web|website|directions|menu|pesan|order online|\d{1,6})$", re.I)
RE_NO_REVIEWS = re.compile(r"tidak ada ulasan|no reviews", re.I)
RE_HOURS_TOKEN = re.compile(
    r"^(buka|tutup|ditutup|open|closed|closes|opens|24 jam|24 hours)", re.I
)
RE_PERM_CLOSED = re.compile(r"tutup permanen|ditutup permanen|permanently closed", re.I)
RE_TEMP_CLOSED = re.compile(r"tutup sementara|ditutup sementara|temporarily closed", re.I)

# --- Deteksi blokir -----------------------------------------------------------------
BLOCK_URL_PARTS = ("/sorry/", "consent.google.com", "accounts.google.com/v3/signin")
BLOCK_TEXT_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"unusual traffic",
        r"lalu lintas yang tidak biasa",
        r"our systems have detected",
        r"sistem kami mendeteksi",
        r"i'?m not a robot",
        r"bukan robot",
        r"recaptcha",
    )
]
BLOCK_SELECTORS = ["form#captcha-form", "iframe[src*='recaptcha']", "#recaptcha"]

# halaman "tidak ada hasil" (bukan error)
NO_RESULTS_PATTERNS = [
    re.compile(p, re.I)
    for p in (r"google maps tidak dapat menemukan", r"google maps can'?t find")
]
NO_RESULTS_JS = r"google maps tidak dapat menemukan|google maps can.?t find"

# tanda akhir daftar hasil (id & en)
END_OF_LIST_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"anda telah mencapai akhir daftar",
        r"you'?ve reached the end of the list",
    )
]


def first_match(root: Tag, candidates: list[str], what: str) -> Tag | None:
    """Coba selector berurutan; log warning bila kandidat utama gagal tapi fallback berhasil."""
    for i, css in enumerate(candidates):
        el = root.select_one(css)
        if el is not None:
            if i > 0:
                log.warning("selector_fallback_used", what=what, used=css, primary=candidates[0])
            return el
    log.warning("selector_not_found", what=what, tried=candidates)
    return None
