"""Uji mandiri bundel PostgreSQL+PostGIS: initdb -> start -> CREATE EXTENSION postgis -> kueri jarak -> stop.

    python selftest_postgres.py --pgsql build/pgsql [--workdir build/selftest] [--port 54399]

Penting: semua proses diluncurkan dengan stdin/stdout/stderr dialihkan. Server Postgres yang
mewarisi pipa pemanggil akan membuat pemanggil menggantung selamanya (masalah nyata di Windows).
Folder kerja sengaja memuat spasi untuk menguji path pengguna Windows yang umum ("Nama Orang").
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run(cmd, env, timeout=120, detached_output=False):
    """detached_output=True untuk perintah yang menyalakan server (pg_ctl start): TIDAK boleh memakai
    pipa, karena proses postgres mewarisinya dan pemanggil menunggu EOF selamanya. Lognya ke file (-l)."""
    if detached_output:
        r = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout, creationflags=NO_WINDOW)
        return r.returncode, ""
    r = subprocess.run(
        cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
        creationflags=NO_WINDOW,
    )
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgsql", required=True, type=Path)
    ap.add_argument("--workdir", type=Path, default=Path("build/selftest dir"))
    ap.add_argument("--port", type=int, default=54399)
    a = ap.parse_args()

    pg = a.pgsql.resolve()
    work = a.workdir.resolve()
    data = work / "pg data"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    pw = work / "pw.txt"
    pw.write_text("selftest-pw", encoding="utf-8")
    env = {**os.environ, "PATH": f"{pg / 'bin'}{os.pathsep}{os.environ['PATH']}", "PGPASSWORD": "selftest-pw"}

    def step(name, cmd, timeout=120, ok=(0,), detached_output=False):
        code, out = run(cmd, env, timeout, detached_output)
        print(f"[{'OK' if code in ok else 'GAGAL'}] {name}" + ("" if code in ok else f"\n{out}"))
        if code not in ok:
            raise SystemExit(1)
        return out

    started = False
    try:
        step("initdb", [str(pg / "bin/initdb.exe"), "-D", str(data), "-U", "petatoko", "--auth=scram-sha-256",
                        f"--pwfile={pw}", "-E", "UTF8", "--locale=C", "--no-instructions"])
        step("pg_ctl start", [str(pg / "bin/pg_ctl.exe"), "start", "-D", str(data), "-w", "-t", "90",
                              "-l", str(work / "postgres.log"), "-o", f"-p {a.port} -c listen_addresses=127.0.0.1"],
             detached_output=True)
        started = True
        base = [str(pg / "bin/psql.exe"), "-h", "127.0.0.1", "-p", str(a.port), "-U", "petatoko", "-tA", "-v", "ON_ERROR_STOP=1"]
        step("CREATE DATABASE", base + ["-d", "postgres", "-c", "create database petatoko"])
        out = step("CREATE EXTENSION postgis", base + ["-d", "petatoko", "-c", "create extension postgis; select postgis_version()"])
        print("      PostGIS:", out.splitlines()[-1])
        out = step("ST_Distance (geography)", base + ["-d", "petatoko", "-c",
                   "select round((st_distance('SRID=4326;POINT(107.6 -6.9)'::geography,'SRID=4326;POINT(107.6 -6.91)'::geography)/1000)::numeric,2)"])
        assert out.strip() == "1.11", out
        step("GIST index pada geography", base + ["-d", "petatoko", "-c",
             "create table t(g geography(point,4326)); create index on t using gist(g); insert into t values ('SRID=4326;POINT(1 2)'); select count(*) from t"])
        print("SEMUA OK")
        return 0
    finally:
        if started:
            code, out = run([str(pg / "bin/pg_ctl.exe"), "stop", "-D", str(data), "-m", "fast", "-w", "-t", "60"], env)
            print(f"[{'OK' if code == 0 else 'GAGAL'}] pg_ctl stop")
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
