"""Parser murni (tanpa browser): HTML -> dataclass. Diuji dengan fixture di tests/fixtures."""
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from app.logging import get_logger
from app.scraper import selectors as sel

log = get_logger("scraper.parser")

RE_FID = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", re.I)
RE_FID_FALLBACK = re.compile(r"(0x[0-9a-f]+:0x[0-9a-f]+)", re.I)
RE_LAT = re.compile(r"!3d(-?\d+\.\d+)")
RE_LNG = re.compile(r"!4d(-?\d+\.\d+)")
RE_AT = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
RE_HAS_ALNUM = re.compile(r"[0-9A-Za-z]")

OPERATIONAL = "operational"
CLOSED_PERMANENTLY = "closed_permanently"
CLOSED_TEMPORARILY = "closed_temporarily"


@dataclass
class PlaceData:
    google_place_key: str
    nama: str
    maps_url: str | None = None
    kategori_google: str | None = None
    rating: float | None = None
    review_count: int | None = None
    alamat: str | None = None
    telepon: str | None = None
    website: str | None = None
    lat: float | None = None
    lng: float | None = None
    jam_buka: dict | None = None
    status_bisnis: str = OPERATIONAL

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UrlInfo:
    key: str | None
    lat: float | None
    lng: float | None


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# --- helper angka ---------------------------------------------------------------------
def parse_float(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def parse_count(text: str) -> int | None:
    """'1.234' -> 1234, '1,2 rb' -> 1200, '3K' -> 3000. Tahan format id/en."""
    t = text.strip().lower().replace(" ", "")
    mult = 1
    if t.endswith(("rb", "k")):
        mult = 1000
        t = t.rstrip("rbk")
    elif t.endswith("jt"):
        mult = 1_000_000
        t = t[:-2]
    if mult > 1:
        val = parse_float(t)
        return round(val * mult) if val is not None else None
    digits = re.sub(r"[.,]", "", t)
    return int(digits) if digits.isdigit() else None


# --- URL -----------------------------------------------------------------------------
def parse_place_url(url: str) -> UrlInfo:
    """Ambil place identifier (FID 0x..:0x..) dan koordinat dari URL Google Maps.

    Koordinat akurat berasal dari pola !3d<lat>!4d<lng>; fallback ke @lat,lng (pusat viewport).
    """
    url = unquote(url)
    m = RE_FID.search(url) or RE_FID_FALLBACK.search(url)
    lat = RE_LAT.search(url)
    lng = RE_LNG.search(url)
    if lat and lng:
        return UrlInfo(m.group(1) if m else None, float(lat.group(1)), float(lng.group(1)))
    at = RE_AT.search(url)
    if at:
        return UrlInfo(m.group(1) if m else None, float(at.group(1)), float(at.group(2)))
    return UrlInfo(m.group(1) if m else None, None, None)


# --- rating & ulasan -----------------------------------------------------------------
def parse_rating_and_reviews(root: Tag) -> tuple[float | None, int | None]:
    """Rating dari aria-label '4,5 bintang'; jumlah ulasan dari aria-label '... 120 Ulasan'
    atau token '(120)' tepat setelah rating. Di tampilan terbatas (tanpa login) Google tidak
    menampilkan jumlah ulasan -> None. 'Tidak ada ulasan' -> 0."""
    rating = reviews = None
    for img in root.select(sel.RATING_IMG[0]):
        label = img.get("aria-label", "")
        m = sel.RE_RATING_LABEL.search(label)
        if not m:
            continue
        rating = parse_float(m.group(1))
        r = sel.RE_REVIEWS_LABEL.search(label)
        if r:
            reviews = parse_count(r.group(1))
        break

    if reviews is None:
        tokens = [t.strip() for t in root.stripped_strings]
        if rating is not None:
            for i, tok in enumerate(tokens):
                if parse_float(tok) == rating and i + 1 < len(tokens):
                    p = sel.RE_REVIEWS_PAREN.match(tokens[i + 1])
                    if p:
                        reviews = parse_count(p.group(1))
                    break
        if rating is None and any(sel.RE_NO_REVIEWS.search(t) for t in tokens):
            reviews = 0
    return rating, reviews


# --- kartu hasil pencarian ---------------------------------------------------------------
def _clean_tokens(card: Tag, name: str) -> list[str]:
    """Teks kartu tanpa nama, tanda '·', dan token ikon (tanpa huruf/angka)."""
    out: list[str] = []
    for raw in card.stripped_strings:
        t = raw.strip().lstrip("·").strip()
        if not t or not RE_HAS_ALNUM.search(t) or t == name:
            continue
        out.append(t)
    return out


def parse_card(card: Tag) -> PlaceData | None:
    link = card.select_one(sel.RESULT_LINK[0])
    if link is None:
        return None
    href = link.get("href", "")
    info = parse_place_url(href)
    name = (link.get("aria-label") or "").strip()
    if not name or not info.key:
        log.warning("card_skipped", reason="no_name_or_key", href=href[:120])
        return None

    place = PlaceData(
        google_place_key=info.key,
        nama=name,
        maps_url=href,
        lat=info.lat,
        lng=info.lng,
    )
    place.rating, place.review_count = parse_rating_and_reviews(card)

    tokens = _clean_tokens(card, name)
    rating_txt = None
    if place.rating is not None:
        rating_txt = next((t for t in tokens if parse_float(t) == place.rating), None)

    hours: list[str] = []
    info_tokens: list[str] = []
    for t in tokens:
        if t == rating_txt or sel.RE_NO_REVIEWS.search(t) or sel.RE_REVIEWS_PAREN.match(t):
            continue
        if sel.RE_JUNK_TOKEN.match(t):
            continue
        if sel.RE_PHONE.match(t):
            place.telepon = t
        elif sel.RE_HOURS_TOKEN.match(t):
            hours.append(t)
        else:
            info_tokens.append(t)

    if info_tokens:
        place.kategori_google = info_tokens[0]
    if len(info_tokens) > 1:
        place.alamat = info_tokens[1]
    if hours:
        place.jam_buka = {"ringkasan": " · ".join(hours)}

    blob = " ".join(tokens)
    if sel.RE_PERM_CLOSED.search(blob):
        place.status_bisnis = CLOSED_PERMANENTLY
    elif sel.RE_TEMP_CLOSED.search(blob):
        place.status_bisnis = CLOSED_TEMPORARILY
    return place


@dataclass
class FeedResult:
    places: list[PlaceData] = field(default_factory=list)
    end_of_list: bool = False
    card_count: int = 0


def parse_feed(html: str) -> FeedResult:
    doc = soup(html)
    feed = sel.first_match(doc, sel.FEED, "feed")
    if feed is None:
        return FeedResult()

    cards = feed.select(sel.RESULT_CARD[0])
    if not cards:  # fallback: induk dari tiap link hasil
        cards = [a.parent for a in feed.select(sel.RESULT_LINK[0]) if a.parent]
        if cards:
            log.warning("selector_fallback_used", what="result_card", used="parent_of_link")

    seen: dict[str, PlaceData] = {}
    for card in cards:
        p = parse_card(card)
        if p and p.google_place_key not in seen:  # feed kadang menampilkan duplikat
            seen[p.google_place_key] = p

    text = feed.get_text(" ", strip=True)
    end = any(p.search(text) for p in sel.END_OF_LIST_PATTERNS)
    return FeedResult(places=list(seen.values()), end_of_list=end, card_count=len(cards))


# --- panel detail -----------------------------------------------------------------------------
def _strip_label_prefix(label: str) -> str:
    return re.sub(r"^[^:]{1,30}:\s*", "", label).strip()


def parse_hours_table(root: Tag) -> dict[str, str]:
    table = sel.first_match(root, sel.DETAIL_HOURS_TABLE, "hours_table")
    if table is None:
        return {}
    out: dict[str, str] = {}
    for tr in table.select("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            day = tds[0].get_text(" ", strip=True)
            hrs = tds[1].get_text(" ", strip=True)
            if day:
                out[day] = hrs
    return out


def parse_detail(html: str, url: str | None = None) -> PlaceData | None:
    """Parse panel detail. `url` = URL halaman saat panel terbuka (memuat !3d/!4d dan FID)."""
    doc = soup(html)
    roots = doc.select(sel.DETAIL_ROOT[0])
    root = roots[-1] if roots else None
    if root is None:
        log.warning("selector_not_found", what="detail_root", tried=sel.DETAIL_ROOT)
        return None

    name = root.get("aria-label", "").strip()
    info = parse_place_url(url) if url else UrlInfo(None, None, None)
    place = PlaceData(
        google_place_key=info.key or "", nama=name, maps_url=url, lat=info.lat, lng=info.lng
    )

    el = sel.first_match(root, sel.DETAIL_ADDRESS, "detail_address")
    if el:
        place.alamat = _strip_label_prefix(el.get("aria-label", "")) or el.get_text(strip=True)
    el = root.select_one(sel.DETAIL_PHONE[0])  # tidak semua tempat punya telepon: bukan error
    if el:
        place.telepon = _strip_label_prefix(el.get("aria-label", "")) or None
    el = root.select_one(sel.DETAIL_WEBSITE[0])  # tidak semua tempat punya website: bukan error
    if el:
        place.website = el.get("href") or _strip_label_prefix(el.get("aria-label", ""))
    el = sel.first_match(root, sel.DETAIL_CATEGORY, "detail_category")
    if el:
        place.kategori_google = el.get_text(strip=True) or None

    place.rating, place.review_count = parse_rating_and_reviews(root)
    weekly = parse_hours_table(root)
    if weekly:
        place.jam_buka = {"jadwal": weekly}  # tampilan terbatas: biasanya hanya hari ini

    text = root.get_text(" ", strip=True)
    if sel.RE_PERM_CLOSED.search(text):
        place.status_bisnis = CLOSED_PERMANENTLY
    elif sel.RE_TEMP_CLOSED.search(text):
        place.status_bisnis = CLOSED_TEMPORARILY
    return place


# --- deteksi blokir -----------------------------------------------------------------------------
def detect_block(url: str, html: str) -> str | None:
    """Kembalikan alasan blokir (str) bila halaman captcha/unusual traffic/consent, else None."""
    for part in sel.BLOCK_URL_PARTS:
        if part in url:
            return f"url mengandung {part}"
    doc = soup(html)
    for css in sel.BLOCK_SELECTORS:
        if doc.select_one(css):
            return f"elemen captcha ({css})"
    # hanya periksa teks bila tidak ada feed/detail (hindari false positive dari nama toko)
    if not doc.select_one(sel.FEED[0]) and not doc.select_one(sel.DETAIL_ROOT[0]):
        body = doc.get_text(" ", strip=True)
        for pat in sel.BLOCK_TEXT_PATTERNS:
            if pat.search(body):
                return f"teks cocok '{pat.pattern}'"
    return None


def merge_detail(base: PlaceData, detail: PlaceData) -> PlaceData:
    """Lengkapi data kartu dengan hasil detail (detail menang bila terisi)."""
    for f in ("kategori_google", "rating", "review_count", "alamat", "telepon", "website"):
        v = getattr(detail, f)
        if v not in (None, ""):
            setattr(base, f, v)
    if detail.jam_buka:
        base.jam_buka = {**(base.jam_buka or {}), **detail.jam_buka}
    if detail.status_bisnis != OPERATIONAL:
        base.status_bisnis = detail.status_bisnis
    return base
