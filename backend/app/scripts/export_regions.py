"""Ekspor tabel regions ke app/desktop/data/regions.csv.gz (data awal edisi Windows, tanpa internet).

    python -m app.scripts.export_regions

Sumber: dataset emsifa/api-wilayah-indonesia (MIT) yang sudah di-seed ke database.
Hasil dibuat deterministik (urut level lalu kode, mtime gzip = 0) agar diff git bersih.
"""
import csv
import gzip
import io
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Region

OUT = Path(__file__).resolve().parents[1] / "desktop" / "data" / "regions.csv.gz"


def main() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(Region.kode, Region.nama, Region.level, Region.parent_kode).order_by(Region.level, Region.kode)
        ).all()
    if len(rows) < 80_000:
        raise SystemExit(f"hanya {len(rows)} wilayah di database; jalankan seed_regions sampai level desa dulu")
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["kode", "nama", "level", "parent_kode"])
    for r in rows:
        w.writerow([r.kode, r.nama, r.level, r.parent_kode or ""])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(buf.getvalue().encode("utf-8"))
    print(f"{len(rows)} wilayah -> {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
