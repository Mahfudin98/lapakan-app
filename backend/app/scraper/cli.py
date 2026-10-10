"""CLI scraper standalone (satu query, tanpa DB).

    python -m app.scraper.cli "toko kosmetik di Andir, Kota Bandung" --max-results 20
    python -m app.scraper.cli "salon di Coblong, Kota Bandung" --detail --json /data/out.json
"""
import argparse
import asyncio
import json
import sys

from app.config import get_settings
from app.logging import setup_logging
from app.scraper.maps import BlockedError, MapsScraper, ScrapeConfig, ScrapeError


def print_table(places) -> None:
    print(f"\n{len(places)} tempat:\n")
    for i, p in enumerate(places, 1):
        coord = f"{p.lat:.6f},{p.lng:.6f}" if p.lat is not None else "-"
        print(
            f"{i:>3}. {p.nama}\n"
            f"     kategori : {p.kategori_google or '-'}\n"
            f"     rating   : {p.rating if p.rating is not None else '-'}"
            f"  ulasan: {p.review_count if p.review_count is not None else '-'}\n"
            f"     alamat   : {p.alamat or '-'}\n"
            f"     telepon  : {p.telepon or '-'}   website: {p.website or '-'}\n"
            f"     koordinat: {coord}   status: {p.status_bisnis}\n"
            f"     key      : {p.google_place_key}"
        )


async def run(args) -> int:
    cfg = ScrapeConfig.from_settings(
        max_results=args.max_results, detail=args.detail, headless=not args.headed
    )
    if args.delay_min is not None:
        cfg.delay_min = args.delay_min
    if args.delay_max is not None:
        cfg.delay_max = args.delay_max

    async def progress(info: dict) -> None:
        print(f"[progres] {info}", file=sys.stderr)

    try:
        async with MapsScraper(cfg, on_progress=progress) as scraper:
            places = await scraper.search(args.query)
    except BlockedError as exc:
        print(f"\nBLOCKED: {exc}", file=sys.stderr)
        return 2
    except ScrapeError as exc:
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        return 1

    print_table(places)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in places], f, ensure_ascii=False, indent=2)
        print(f"\nJSON disimpan ke {args.json}")
    return 0


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser(description="Scrape satu query Google Maps")
    ap.add_argument("query", help='contoh: "toko kosmetik di Andir, Kota Bandung"')
    ap.add_argument("--max-results", type=int, default=s.scrape_max_results_default)
    ap.add_argument("--detail", action="store_true", help="klik tiap hasil (lebih lambat)")
    ap.add_argument("--json", help="simpan hasil ke file JSON")
    ap.add_argument("--delay-min", type=float)
    ap.add_argument("--delay-max", type=float)
    ap.add_argument("--headed", action="store_true", help="tampilkan browser (butuh display)")
    args = ap.parse_args()
    setup_logging(s.log_level)
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
