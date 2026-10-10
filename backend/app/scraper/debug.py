from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from app.logging import get_logger

log = get_logger("scraper.debug")


async def dump_page(page: Page, debug_dir: str, tag: str) -> str | None:
    """Simpan screenshot + HTML saat scraper gagal. Mengembalikan prefix file (atau None)."""
    try:
        d = Path(debug_dir)
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)[:60]
        prefix = d / f"{stamp}-{safe}"
        await page.screenshot(path=f"{prefix}.png", full_page=False)
        Path(f"{prefix}.html").write_text(await page.content(), encoding="utf-8")
        log.error("debug_dump_saved", prefix=str(prefix), url=page.url)
        return str(prefix)
    except Exception as exc:  # jangan sampai dump gagal menutupi error aslinya
        log.error("debug_dump_failed", error=str(exc))
        return None
