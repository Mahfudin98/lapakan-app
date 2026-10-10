"""Menyiapkan PostgreSQL portabel + PostGIS inti untuk dibundel ke installer.

    python prepare_postgres.py --pg-zip postgresql.zip --postgis-zip postgis-bundle.zip --out build/pgsql

- Dari zip biner EDB PostgreSQL hanya bin/, lib/, share/ yang diambil (tanpa pgAdmin, dokumentasi, header).
- Dari bundle PostGIS hanya ekstensi `postgis` inti: DLL pendukung, postgis-3.dll, skrip SQL, dan proj.db.
  (Bundle memuat h3, pgrouting, MobilityDB, dll. yang tidak dipakai dan memakan >100 MB.)
- DLL milik PostgreSQL tidak ditimpa oleh DLL dari bundle PostGIS.
Hanya memakai pustaka standar Python, supaya bisa dijalankan dengan Python mana pun.
"""
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path


def extract(zf: zipfile.ZipFile, member: zipfile.ZipInfo, dest: Path, overwrite: bool = True) -> bool:
    if member.is_dir():
        return False
    if dest.exists() and not overwrite:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
    return True


def prepare(pg_zip: Path, postgis_zip: Path, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    stats = {"pg_files": 0, "postgis_files": 0}

    with zipfile.ZipFile(pg_zip) as z:
        for m in z.infolist():
            parts = m.filename.split("/")
            if len(parts) > 2 and parts[0] == "pgsql" and parts[1] in ("bin", "lib", "share"):
                if extract(z, m, out / "/".join(parts[1:])):
                    stats["pg_files"] += 1
        # versi tepat untuk dicatat
        for m in z.infolist():
            if m.filename == "pgsql/doc/postgresql/html/release.html":
                break

    with zipfile.ZipFile(postgis_zip) as z:
        root = next(n.split("/")[0] for n in z.namelist() if "/" in n)
        prefix = root + "/"
        for m in z.infolist():
            name = m.filename[len(prefix):] if m.filename.startswith(prefix) else ""
            if not name or m.is_dir():
                continue
            parts = name.split("/")
            want = False
            overwrite = True
            if parts[0] == "bin" and len(parts) == 2 and name.endswith(".dll"):
                want, overwrite = True, False  # jangan menimpa DLL milik PostgreSQL
            elif name == "lib/postgis-3.dll":
                want = True
            elif parts[0] == "share" and parts[1:2] == ["extension"] and re.fullmatch(
                r"postgis(\.control|--\d+\.\d+\.\d+\.sql)", parts[-1]
            ):
                want = True
            elif name.startswith("share/contrib/postgis-"):
                want = True
            elif name in ("LICENSE", "COPYRIGHT.pg_sphere", "README.txt", "version.txt"):
                want, name = True, f"licenses/postgis-{parts[-1]}"
                extract(z, m, out / name)
                continue
            if want and extract(z, m, out / name, overwrite):
                stats["postgis_files"] += 1
    return stats


# Berkas yang tidak dibutuhkan untuk menjalankan server (pustaka pengembangan, alat uji, GUI, terjemahan).
PRUNE_GLOBS = [
    "bin/wx*.dll",  # pustaka GUI pgAdmin/StackBuilder
    "bin/ecpg.exe", "bin/libecpg*.dll", "bin/libpgtypes.dll",
    "bin/isolationtester.exe", "bin/pg_regress*.exe", "bin/libpq_pipeline.exe", "bin/libpq_testclient.exe",
    "bin/libpq_uri_regress.exe", "bin/*.lib",
    "lib/*.lib", "lib/pgxs", "lib/cmake",
    "share/locale",  # terjemahan pesan; server tetap berbahasa Inggris
    "share/contrib/postgis-*/proj/*.tif",  # grid PROJ nasional; tidak dipakai SRID 4326 (WGS84)
    "share/contrib/postgis-*/proj/*.json",
]


def prune(out: Path) -> int:
    n = 0
    for pattern in PRUNE_GLOBS:
        for path in out.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            n += 1
    return n


def verify(out: Path) -> list[str]:
    problems = []
    for rel in (
        "bin/postgres.exe", "bin/initdb.exe", "bin/pg_ctl.exe", "bin/psql.exe", "bin/pg_isready.exe",
        "lib/postgis-3.dll", "share/extension/postgis.control", "share/postgresql.conf.sample",
    ):
        if not (out / rel).exists():
            problems.append(f"hilang: {rel}")
    if not list((out / "share/extension").glob("postgis--*.sql")):
        problems.append("hilang: share/extension/postgis--<versi>.sql")
    if not list((out / "share/contrib").glob("postgis-*/proj/proj.db")):
        problems.append("hilang: proj.db")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pg-zip", required=True, type=Path)
    ap.add_argument("--postgis-zip", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    stats = prepare(a.pg_zip, a.postgis_zip, a.out)
    stats["pruned"] = prune(a.out)
    size = sum(f.stat().st_size for f in a.out.rglob("*") if f.is_file()) / 1e6
    print(f"PostgreSQL: {stats['pg_files']} file, PostGIS: {stats['postgis_files']} file, dipangkas: {stats['pruned']}, total {size:.0f} MB -> {a.out}")
    problems = verify(a.out)
    for p in problems:
        print("MASALAH:", p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
