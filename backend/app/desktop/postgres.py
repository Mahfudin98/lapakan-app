"""Mengelola server PostgreSQL portabel milik aplikasi (tanpa layanan Windows, tanpa hak admin).

Catatan penting (Windows):
- Perintah yang menyalakan server (pg_ctl start) TIDAK boleh memakai pipa untuk stdout/stderr:
  proses postgres mewarisinya sehingga pemanggil yang menunggu EOF akan menggantung selamanya.
  Log server ditulis ke file lewat opsi -l.
- Server hanya mendengarkan 127.0.0.1 dan memakai autentikasi scram-sha-256 dengan kata sandi acak.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

from app.desktop.config import DesktopConfig
from app.desktop.paths import Layout, ascii_alias, release_aliases
from app.logging import get_logger

log = get_logger("desktop.postgres")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class PostgresError(RuntimeError):
    pass


def tail(path: Path, lines: int = 15) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


class Postgres:
    def __init__(self, layout: Layout, cfg: DesktopConfig):
        self.layout = layout
        self.cfg = cfg
        self.log_file = layout.logs / "postgres.log"
        # path yang diberikan KE PostgreSQL (argumen baris perintah = ANSI): alias ASCII bila perlu
        try:
            self.root = ascii_alias(layout.data) if layout.data.exists() else layout.data
        except OSError as exc:
            raise PostgresError(
                "Folder data memuat karakter yang tidak didukung PostgreSQL di Windows ini dan alias drive gagal "
                f"dibuat ({exc}). Pasang ulang dengan folder data berhuruf Latin biasa, mis. C:\\PetaToko."
            ) from exc
        self.pg_data = self.root / "pgdata"
        self.pg_log = self.root / "logs" / "postgres.log"
        self.pg_run = self.root / "run"

    # --- util proses ---
    def _exe(self, name: str) -> str:
        p = self.layout.pg_bin / f"{name}.exe"
        if not p.exists():
            raise PostgresError(f"komponen database tidak ditemukan: {p}")
        return str(p)

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PATH"] = f"{self.layout.pg_bin}{os.pathsep}{env.get('PATH', '')}"
        env["PGPASSWORD"] = self.cfg.db_password
        return env

    def _run(self, args: list[str], timeout: float = 120, detached: bool = False) -> tuple[int, str]:
        kwargs = dict(env=self._env(), stdin=subprocess.DEVNULL, timeout=timeout, creationflags=NO_WINDOW)
        if detached:
            r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
            return r.returncode, ""
        r = subprocess.run(args, capture_output=True, text=True, errors="replace", **kwargs)
        return r.returncode, (r.stdout + r.stderr).strip()

    # --- status ---
    @property
    def data(self) -> str:
        return str(self.pg_data)

    def release(self) -> None:
        """Lepaskan alias drive (bila ada). Panggil hanya setelah server dimatikan."""
        release_aliases()

    def initialized(self) -> bool:
        return (self.layout.pgdata / "PG_VERSION").exists()

    def running_port(self) -> int | None:
        """Port server yang sedang berjalan untuk folder data ini (dari postmaster.pid), atau None."""
        code, _ = self._run([self._exe("pg_ctl"), "status", "-D", self.data], timeout=30)
        if code != 0:
            return None
        try:
            lines = (self.layout.pgdata / "postmaster.pid").read_text(encoding="utf-8").splitlines()
            return int(lines[3])
        except (OSError, ValueError, IndexError):
            return None

    # --- siklus hidup ---
    def init(self) -> None:
        """initdb. Bila gagal di tengah jalan, folder setengah jadi dihapus agar percobaan ulang bersih."""
        if self.initialized():
            return
        if self.layout.pgdata.exists() and any(self.layout.pgdata.iterdir()):
            raise PostgresError(f"folder database tidak kosong tetapi bukan database valid: {self.layout.pgdata}")
        self.layout.run.mkdir(parents=True, exist_ok=True)
        pwfile = self.layout.run / "initdb.pw"
        pwfile.write_text(self.cfg.db_password, encoding="utf-8")
        pw_arg = self.pg_run / "initdb.pw"
        try:
            code, out = self._run(
                [self._exe("initdb"), "-D", self.data, "-U", self.cfg.db_user, "--auth=scram-sha-256",
                 f"--pwfile={pw_arg}", "-E", "UTF8", "--locale=C", "--no-instructions"],
                timeout=300,
            )
        finally:
            pwfile.unlink(missing_ok=True)  # kata sandi jangan tertinggal di disk selain di config.json
        if code != 0:
            shutil.rmtree(self.layout.pgdata, ignore_errors=True)
            raise PostgresError(f"initdb gagal (kode {code}): {out[-600:]}")
        conf = self.layout.pgdata / "postgresql.conf"
        with open(conf, "a", encoding="utf-8") as fh:
            fh.write("\n# --- Peta Toko ---\nlisten_addresses = '127.0.0.1'\nmax_connections = 60\n")
        log.info("initdb_done", data=self.data)

    def start(self) -> None:
        running = self.running_port()
        if running == self.cfg.pg_port:
            return
        if running is not None:  # berjalan di port lain (konfigurasi berubah): mulai ulang
            self.stop()
        self.layout.logs.mkdir(parents=True, exist_ok=True)
        if self.log_file.exists() and self.log_file.stat().st_size > 10_000_000:
            self.log_file.replace(self.log_file.with_suffix(".log.old"))
        code, _ = self._run(
            [self._exe("pg_ctl"), "start", "-D", self.data, "-w", "-t", "90", "-l", str(self.pg_log),
             "-o", f"-p {self.cfg.pg_port} -c listen_addresses=127.0.0.1"],
            timeout=150, detached=True,
        )
        if code != 0:
            raise PostgresError(f"database gagal dijalankan (kode {code}). Log:\n{tail(self.log_file)}")
        self.wait_ready(30)

    def stop(self) -> None:
        if not self.initialized() or self.running_port() is None:
            return
        code, out = self._run([self._exe("pg_ctl"), "stop", "-D", self.data, "-m", "fast", "-w", "-t", "60"], timeout=90)
        if code != 0:
            log.warning("pg_stop_failed", code=code, out=out[-300:])

    def connect(self, dbname: str | None = None, timeout: int = 5):
        import psycopg

        return psycopg.connect(
            host="127.0.0.1", port=self.cfg.pg_port, user=self.cfg.db_user, password=self.cfg.db_password,
            dbname=dbname or self.cfg.db_name, connect_timeout=timeout, autocommit=True,
        )

    def wait_ready(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with self.connect("postgres"):
                    return
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(0.5)
        raise PostgresError(f"database tidak merespons di port {self.cfg.pg_port}: {last}\n{tail(self.log_file)}")

    def ensure_database(self) -> None:
        with self.connect("postgres") as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.cfg.db_name,)).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{self.cfg.db_name}"')
                log.info("database_created", name=self.cfg.db_name)
