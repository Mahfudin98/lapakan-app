"""Driver Playwright untuk Google Maps (publik, tanpa login).

Aturan "sopan":
- 1 browser, 1 halaman, tidak paralel.
- Jeda acak delay_min..delay_max detik di antara aksi.
- Batas hasil per query (max_results).
- Captcha / "unusual traffic" / halaman blokir -> BlockedError. TIDAK ada upaya bypass.
"""
import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import TimeoutError as PWTimeout

from app.config import get_settings
from app.logging import get_logger
from app.scraper import parser
from app.scraper import selectors as sel
from app.scraper.debug import dump_page
from app.scraper.parser import PlaceData

log = get_logger("scraper.maps")

SEARCH_URL = "https://www.google.com/maps/search/{query}?hl=id"
MAX_STALLED_SCROLLS = 3

ProgressCb = Callable[[dict], Awaitable[None] | None]
CancelCb = Callable[[], Awaitable[bool] | bool]


class ScrapeError(Exception):
    """Kegagalan scraping (selector rusak, timeout, dll). Debug dump sudah disimpan."""


class BlockedError(ScrapeError):
    """Terdeteksi captcha / blokir. Job harus dihentikan dan ditandai 'blocked'."""


class CancelledError(ScrapeError):
    pass


@dataclass
class ScrapeConfig:
    max_results: int = 200
    detail: bool = False
    headless: bool = True
    delay_min: float = 2.0
    delay_max: float = 5.0
    debug_dir: str = "/data/debug"

    @classmethod
    def from_settings(cls, **overrides) -> "ScrapeConfig":
        s = get_settings()
        base = dict(
            max_results=s.scrape_max_results_default,
            delay_min=s.scrape_delay_min,
            delay_max=s.scrape_delay_max,
            debug_dir=s.debug_dir,
        )
        return cls(**{**base, **overrides})


async def _maybe_await(value):
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


class MapsScraper:
    def __init__(
        self,
        config: ScrapeConfig,
        on_progress: ProgressCb | None = None,
        should_cancel: CancelCb | None = None,
    ):
        self.cfg = config
        self.on_progress = on_progress
        self.should_cancel = should_cancel
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None
        self.page: Page | None = None

    # --- lifecycle -----------------------------------------------------------------
    async def _launch_browser(self) -> Browser:
        """Chromium bawaan Playwright (Docker), atau Edge/Chrome yang sudah terpasang (edisi Windows)."""
        mode = (get_settings().scrape_browser or "").strip().lower()
        if mode in ("", "chromium"):
            candidates: list[str | None] = [None]
        elif mode == "auto":
            candidates = ["msedge", "chrome", None]  # Edge ada di setiap Windows 10/11
        else:
            candidates = [mode]
        last: Exception | None = None
        for channel in candidates:
            try:
                kwargs = {"channel": channel} if channel else {}
                browser = await self._pw.chromium.launch(headless=self.cfg.headless, **kwargs)
                log.info("browser_launched", channel=channel or "chromium")
                return browser
            except Exception as exc:  # noqa: BLE001 - coba kandidat berikutnya
                last = exc
                log.warning("browser_launch_failed", channel=channel or "chromium", error=str(exc)[:300])
        raise ScrapeError(
            "Browser untuk scraping tidak ditemukan. Pasang Microsoft Edge atau Google Chrome, "
            f"lalu jalankan ulang. Detail: {str(last)[:200]}"
        )

    async def __aenter__(self) -> "MapsScraper":
        self._pw = await async_playwright().start()
        try:
            self._browser = await self._launch_browser()
        except BaseException:
            await self._pw.stop()
            self._pw = None
            raise
        self._ctx = await self._browser.new_context(
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            viewport={"width": 1366, "height": 900},
        )
        self.page = await self._ctx.new_page()
        return self

    async def __aexit__(self, *exc) -> None:
        for closer in (self._ctx, self._browser):
            if closer:
                try:
                    await closer.close()
                except Exception:
                    pass
        if self._pw:
            await self._pw.stop()

    # --- util ------------------------------------------------------------------------------
    async def _pause(self, lo: float | None = None, hi: float | None = None) -> None:
        await asyncio.sleep(random.uniform(lo or self.cfg.delay_min, hi or self.cfg.delay_max))

    async def pause(self) -> None:
        """Jeda acak antar-aksi (dipakai juga oleh job runner antar-query)."""
        await self._pause()

    async def _emit(self, **info) -> None:
        if self.on_progress:
            await _maybe_await(self.on_progress(info))

    async def _check_cancel(self) -> None:
        if self.should_cancel and await _maybe_await(self.should_cancel()):
            raise CancelledError("dibatalkan oleh user")

    async def _check_block(self) -> None:
        assert self.page
        reason = parser.detect_block(self.page.url, await self.page.content())
        if reason:
            await dump_page(self.page, self.cfg.debug_dir, "blocked")
            log.error("blocked_detected", reason=reason, url=self.page.url)
            raise BlockedError(
                f"Google Maps memblokir/menampilkan captcha ({reason}). "
                "Job dihentikan; coba lagi nanti dengan jeda lebih panjang."
            )

    async def _fail(self, tag: str, msg: str, exc: Exception | None = None) -> ScrapeError:
        assert self.page
        prefix = await dump_page(self.page, self.cfg.debug_dir, tag)
        log.error("scrape_failed", tag=tag, message=msg, debug=prefix)
        return ScrapeError(f"{msg} (debug: {prefix})")

    # --- API utama --------------------------------------------------------------------------------
    async def search(
        self, query: str, on_list: Callable[[list[PlaceData]], Awaitable[None] | None] | None = None
    ) -> list[PlaceData]:
        """Scrape satu query. `on_list` dipanggil begitu daftar hasil ter-parse (sebelum mode detail),
        supaya pemanggil bisa langsung menyimpan/menampilkan hasil awal."""
        assert self.page, "gunakan 'async with MapsScraper(...)'"
        page = self.page
        url = SEARCH_URL.format(query=quote(query))
        log.info("search_start", query=query, url=url, detail=self.cfg.detail, max=self.cfg.max_results)
        await self._emit(query=query, phase="loading", found=0)

        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.wait_for_function(
                """([feed, detail, noRes]) => !!document.querySelector(feed)
                    || !!document.querySelector(detail)
                    || new RegExp(noRes, 'i').test(document.body.innerText)""",
                arg=[sel.FEED[0], sel.DETAIL_READY[0], sel.NO_RESULTS_JS],
                timeout=25_000,
            )
        except PWTimeout:
            await self._check_block()
            raise await self._fail("no_feed", f"feed hasil tidak muncul untuk query '{query}'")
        await self._check_block()

        if await page.locator(sel.FEED[0]).count() == 0 and await page.locator(sel.DETAIL_READY[0]).count() == 0:
            log.info("no_results", query=query)
            await self._emit(query=query, phase="done", found=0)
            return []

        if await page.locator(sel.FEED[0]).count() == 0:
            # Google langsung membuka satu tempat (hasil tunggal)
            d = parser.parse_detail(await page.content(), page.url)
            return [d] if d and d.google_place_key else []

        await self._scroll_feed(query)
        res = parser.parse_feed(await page.content())
        places = res.places[: self.cfg.max_results]
        log.info("feed_parsed", query=query, cards=res.card_count, places=len(places), end=res.end_of_list)
        if res.card_count and not places:
            raise await self._fail("parse_zero", "kartu ada tapi tidak ada yang bisa di-parse (selector berubah?)")

        if on_list and places:
            await _maybe_await(on_list(places))
        if self.cfg.detail:
            await self._fill_details(query, places)
        await self._emit(query=query, phase="done", found=len(places))
        return places

    # --- scroll feed -----------------------------------------------------------------------------------
    async def _scroll_feed(self, query: str) -> None:
        page = self.page
        feed = page.locator(sel.FEED[0]).first
        links = page.locator(f"{sel.FEED[0]} {sel.RESULT_LINK[0]}")
        last, stalled = 0, 0
        while True:
            await self._check_cancel()
            count = await links.count()
            await self._emit(query=query, phase="scrolling", found=count)
            text = await feed.inner_text()
            if any(p.search(text) for p in sel.END_OF_LIST_PATTERNS):
                log.info("end_of_list", count=count)
                return
            if count >= self.cfg.max_results:
                log.info("max_results_reached", count=count)
                return
            stalled = stalled + 1 if count == last else 0
            if stalled >= MAX_STALLED_SCROLLS:
                log.info("scroll_stalled", count=count)
                return
            last = count
            await feed.evaluate("e => e.scrollTo(0, e.scrollHeight)")
            await self._pause()
            await self._check_block()

    # --- mode detail -------------------------------------------------------------------------------------------
    async def _fill_details(self, query: str, places: list[PlaceData]) -> None:
        page = self.page
        for i, place in enumerate(places, 1):
            await self._check_cancel()
            await self._emit(query=query, phase="detail", found=len(places), detail_done=i - 1)
            try:
                link = page.locator(f'{sel.FEED[0]} a[href*="{place.google_place_key}"]').first
                await link.scroll_into_view_if_needed(timeout=5_000)
                await link.click(timeout=5_000)
                await page.wait_for_function(
                    """name => [...document.querySelectorAll('[role="main"][aria-label]')]
                                .some(e => e.getAttribute('aria-label') === name)""",
                    arg=place.nama,
                    timeout=15_000,
                )
                await page.wait_for_selector(sel.DETAIL_READY[0] + ", " + sel.DETAIL_READY[1], timeout=8_000)
                await self._expand_hours()
                detail = parser.parse_detail(await page.content(), page.url)
                if detail:
                    parser.merge_detail(place, detail)
                else:
                    log.warning("detail_parse_empty", place=place.nama)
            except PWTimeout:
                await self._check_block()
                log.warning("detail_timeout", place=place.nama)
                await dump_page(page, self.cfg.debug_dir, f"detail_{place.nama}")
            await self._pause()
            await self._check_block()

    async def _expand_hours(self) -> None:
        for css in sel.DETAIL_HOURS_EXPAND:
            loc = self.page.locator(css).first
            try:
                if await loc.count():
                    await loc.click(timeout=2_000)
                    await asyncio.sleep(0.8)
                    return
            except PWTimeout:
                continue
        log.debug("hours_expand_not_found")


def build_query(kategori: str, *wilayah: str) -> str:
    """'{kategori} di {desa}, {kecamatan}, {kab/kota}, {provinsi}' (bagian kosong dilewati)."""
    parts = [w.strip() for w in wilayah if w and w.strip()]
    return f"{kategori.strip()} di {', '.join(parts)}" if parts else kategori.strip()


__all__ = [
    "BlockedError", "CancelledError", "MapsScraper", "ScrapeConfig", "ScrapeError", "build_query",
]
