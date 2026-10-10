"""Peluncur Peta Toko untuk Windows: ikon di tray, mengelola database + server + worker.

    PetaToko.exe -m app.desktop.launcher             # normal: jalankan semua lalu buka jendela
    PetaToko.exe -m app.desktop.launcher --background  # tanpa membuka jendela (mis. saat Windows mulai)
    PetaToko.exe -m app.desktop.launcher --stop        # minta instance yang berjalan berhenti (dipakai installer)

Alur: setup (bila belum lengkap) -> database -> migrasi -> API + worker -> tunggu siap -> buka jendela.
"""
import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from ctypes import wintypes
from pathlib import Path

from app.desktop import APP_VERSION, browser, config, setup
from app.desktop.paths import Layout, release_aliases
from app.desktop.postgres import Postgres, PostgresError
from app.logging import setup_logging

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TITLE = "Peta Toko"
MAX_RESTARTS = 5  # per anak proses dalam 10 menit

user32 = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None


# ---------------------------------------------------------------- utilitas Windows
def message_box(text: str, icon: int = 0x40, buttons: int = 0) -> int:
    """0x10 error, 0x30 peringatan, 0x40 info, 0x20 tanya; buttons 0=OK, 4=Ya/Tidak. 6 = Ya."""
    if user32 is None:
        print(text)
        return 6
    return user32.MessageBoxW(None, text, TITLE, icon | buttons | 0x10000)  # MB_SETFOREGROUND


def pid_alive(pid: int) -> bool:
    if kernel32 is None or pid <= 0:
        return False
    kernel32.OpenProcess.restype = wintypes.HANDLE
    h = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not h:
        return False
    try:
        return kernel32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT: masih berjalan
    finally:
        kernel32.CloseHandle(h)


class SingleInstance:
    """Mutex bernama per folder data: satu peluncur per set data."""

    def __init__(self, data_dir: Path):
        digest = hashlib.sha1(str(data_dir).lower().encode("utf-8")).hexdigest()[:12]
        self.name = f"Local\\PetaToko-{digest}"
        self.handle = None
        self.already_running = False
        if kernel32 is not None:
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            self.already_running = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


# ---------------------------------------------------------------- jendela aplikasi
# Flag penting untuk jendela "mode aplikasi" dengan profil browser khusus:
#  --disable-sync + --disable-features=msImplicitSignin,...  : tanpa dialog "sinkronisasi data penjelajahan"
#       (Edge otomatis memasukkan akun Microsoft Windows ke profil baru);
#  --lang=id + Translate dimatikan                            : tanpa tawaran "Terjemahkan halaman?" dan dialog
#       izin (mis. lokasi) berbahasa Indonesia.
WINDOW_FLAGS = [
    "--no-first-run", "--no-default-browser-check", "--window-size=1280,860", "--lang=id", "--disable-sync",
    "--disable-features=msImplicitSignin,msEdgeSyncConsent,msEdgeOnRampFRE,msEdgeFRE,Translate,TranslateUI,msEdgeTranslate",
]


def window_command(exe: Path, url: str, profile: Path) -> list[str]:
    return [str(exe), f"--app={url}", f"--user-data-dir={profile}", *WINDOW_FLAGS]


def open_app_window(layout: Layout, url: str) -> None:
    exe = browser.find_edge() or browser.find_chrome()
    if exe is None:
        webbrowser.open(url)
        return
    subprocess.Popen(
        window_command(exe, url, layout.browser_profile),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def server_is_healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "health", timeout=3) as r:
            return r.status == 200 and json.loads(r.read()).get("app") == "peta-toko"
    except Exception:  # noqa: BLE001
        return False


def process_image(pid: int) -> str | None:
    """Path berkas .exe sebuah proses (None bila tidak dapat dibaca)."""
    if kernel32 is None or pid <= 0:
        return None
    kernel32.OpenProcess.restype = wintypes.HANDLE
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(h)


# ---------------------------------------------------------------- proses anak
class Child:
    def __init__(self, name: str, argv: list[str], env: dict, cwd: Path, log_path: Path):
        self.name, self.argv, self.env, self.cwd, self.log_path = name, argv, env, cwd, log_path
        self.proc: subprocess.Popen | None = None
        self.starts: list[float] = []

    def start(self) -> None:
        if self.log_path.exists() and self.log_path.stat().st_size > 5_000_000:
            self.log_path.replace(self.log_path.with_suffix(".log.old"))
        fh = open(self.log_path, "ab")
        self.proc = subprocess.Popen(
            self.argv, env=self.env, cwd=str(self.cwd), stdin=subprocess.DEVNULL, stdout=fh,
            stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
        )
        fh.close()  # anak punya salinan handle sendiri
        self.starts.append(time.monotonic())

    @property
    def pid(self) -> int:
        return self.proc.pid if self.proc else 0

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def can_restart(self) -> bool:
        now = time.monotonic()
        self.starts = [t for t in self.starts if now - t < 600]
        return len(self.starts) < MAX_RESTARTS

    def stop(self, timeout: float) -> None:
        if not self.alive():
            return
        deadline = time.monotonic() + timeout
        while self.alive() and time.monotonic() < deadline:
            time.sleep(0.2)
        if self.alive():
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ---------------------------------------------------------------- aplikasi
class App:
    def __init__(self, layout: Layout, background: bool):
        self.layout = layout
        self.background = background
        self.cfg: config.DesktopConfig | None = None
        self.pg: Postgres | None = None
        self.api: Child | None = None
        self.worker: Child | None = None
        self.icon = None
        self.stopping = threading.Event()
        self.ready = threading.Event()
        self.stop_file = layout.run / "launcher.stop"
        self.worker_stop_file = layout.run / "worker.stop"
        self.pids_file = layout.run / "pids.json"

    # -- log
    def log(self, msg: str) -> None:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)

    def tip(self, text: str) -> None:
        self.log(text)
        if self.icon is not None:
            try:
                self.icon.title = f"{TITLE} - {text}"[:127]
            except Exception:  # noqa: BLE001
                pass

    def notify(self, text: str) -> None:
        if self.icon is not None:
            try:
                self.icon.notify(text, TITLE)
            except Exception:  # noqa: BLE001
                pass

    # -- siklus hidup
    def child_env(self) -> dict:
        assert self.cfg
        env = dict(os.environ)
        env.update(
            DATABASE_URL=self.cfg.database_url,
            PETATOKO_HOME=str(self.layout.app),
            PETATOKO_DATA=str(self.layout.data),
            PETATOKO_STATIC_DIR=str(self.layout.static),
            PETATOKO_STOP_FILE=str(self.worker_stop_file),
            SCRAPE_BROWSER="auto",
            DEBUG_DIR=str(self.layout.debug),
            PLAYWRIGHT_BROWSERS_PATH=str(self.layout.browsers),
            CORS_ORIGINS=self.cfg.app_url.rstrip("/"),
            LOG_LEVEL="INFO",
            PYTHONUTF8="1",
            PYTHONUNBUFFERED="1",
        )
        return env

    def boot(self) -> None:
        try:
            self._boot()
        except Exception as exc:  # noqa: BLE001
            import traceback

            self.log("BOOT GAGAL:\n" + traceback.format_exc())
            message_box(
                f"Peta Toko tidak dapat dijalankan.\n\n{exc}\n\nRincian ada di:\n{self.layout.logs}", 0x10
            )
            self.shutdown()
            if self.icon is not None:
                self.icon.stop()

    def _boot(self) -> None:
        layout = self.layout
        layout.ensure_dirs()
        # 1) peluncur sebelumnya mungkin mati paksa: matikan API/worker yatim (membaca pids.json LAMA) agar port dan
        #    kunci worker bebas; 2) baru catat pid peluncur ini, sejak awal, supaya `--stop` dapat mematikannya
        #    walau boot macet (mis. menunggu dialog galat).
        self.cleanup_orphans()
        self.write_pids()
        if not setup.is_complete(layout):
            self.tip("menyiapkan database untuk pertama kali (1-2 menit)…")
            self.notify("Menyiapkan database untuk pertama kali. Ini hanya sekali dan butuh 1-2 menit.")
            rep = setup.Reporter(layout, None)
            setup.run_setup(layout, rep, download_browser=True)

        self.cfg = config.load(layout)
        if self.cfg is None:
            raise config.ConfigError("konfigurasi tidak ditemukan; jalankan ulang aplikasi")
        os.environ["DATABASE_URL"] = self.cfg.database_url
        from app.config import get_settings

        get_settings.cache_clear()

        self.tip("menjalankan database…")
        self.pg = Postgres(layout, self.cfg)
        if self.pg.running_port() is None and not config.port_is_free(self.cfg.pg_port):
            self.cfg.pg_port = config.find_free_port(self.cfg.pg_port + 1, avoid=(self.cfg.app_port,))
            config.save(layout, self.cfg)
            os.environ["DATABASE_URL"] = self.cfg.database_url
            get_settings.cache_clear()
            self.pg = Postgres(layout, self.cfg)
        self.pg.start()
        self.pg.ensure_database()
        setup.migrate(layout)  # idempoten; menangani pembaruan aplikasi yang menambah tabel/kolom

        if not config.port_is_free(self.cfg.app_port):
            self.cfg.app_port = config.find_free_port(self.cfg.app_port + 1, avoid=(self.cfg.pg_port,))
            config.save(layout, self.cfg)

        self.tip("menjalankan server…")
        self.worker_stop_file.unlink(missing_ok=True)
        self.stop_file.unlink(missing_ok=True)
        env = self.child_env()
        py = str(layout.python)
        self.api = Child(
            "api",
            [py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.cfg.app_port),
             "--log-level", "warning"],
            env, layout.backend, layout.logs / "api.log",
        )
        self.worker = Child("worker", [py, "-m", "app.workers.runner"], env, layout.backend, layout.logs / "worker.log")
        self.api.start()
        self.worker.start()
        self.write_pids()
        self.wait_healthy(90)

        self.ready.set()
        self.tip("siap")
        if not self.background:
            self.open_window()
        else:
            self.notify("Peta Toko berjalan di latar belakang. Klik ikon di dekat jam untuk membukanya.")
        self.supervise()

    def cleanup_orphans(self) -> None:
        """Peluncur sebelumnya mati paksa (mis. proses di-kill/listrik padam saat aplikasi di-restart): API dan worker-nya
        bisa masih hidup dan menahan port/kunci worker. Matikan HANYA bila benar-benar milik instalasi ini."""
        try:
            pids = json.loads(self.pids_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        app_root = str(self.layout.app).lower()
        for key in ("api", "worker"):
            pid = int(pids.get(key, 0) or 0)
            image = process_image(pid) if pid and pid_alive(pid) else None
            if image and image.lower().startswith(app_root):  # cegah salah bunuh akibat PID yang dipakai ulang
                self.log(f"mematikan proses {key} yatim (pid {pid})")
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
        self.pids_file.unlink(missing_ok=True)

    def write_pids(self) -> None:
        data = {"launcher": os.getpid(), "api": self.api.pid if self.api else 0, "worker": self.worker.pid if self.worker else 0}
        try:
            self.pids_file.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    def wait_healthy(self, seconds: float) -> None:
        assert self.cfg and self.api
        deadline = time.monotonic() + seconds
        url = self.cfg.app_url + "health"
        while time.monotonic() < deadline:
            if not self.api.alive():
                raise RuntimeError(f"server berhenti mendadak. Log:\n{_tail(self.layout.logs / 'api.log')}")
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    if r.status == 200 and json.loads(r.read()).get("app") == "peta-toko":
                        return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        raise RuntimeError(f"server tidak siap dalam {int(seconds)} detik. Log:\n{_tail(self.layout.logs / 'api.log')}")

    def supervise(self) -> None:
        while not self.stopping.is_set():
            if self.stop_file.exists():
                self.log("permintaan berhenti diterima (launcher.stop)")
                self.shutdown()
                if self.icon is not None:
                    self.icon.stop()
                return
            for child in (self.api, self.worker):
                if child and not child.alive() and not self.stopping.is_set():
                    self.log(f"{child.name} berhenti (kode {child.proc.returncode if child.proc else '?'})")
                    if child.can_restart():
                        child.start()
                        self.write_pids()
                        self.notify(f"Komponen {child.name} dimulai ulang.")
                    elif not getattr(child, "gave_up", False):
                        child.gave_up = True
                        self.notify(f"Komponen {child.name} terus berhenti. Lihat log di folder data.")
            time.sleep(1.0)

    # -- jendela & menu
    def open_window(self) -> None:
        assert self.cfg
        open_app_window(self.layout, self.cfg.app_url)

    def open_folder(self, path: Path) -> None:
        os.startfile(str(path))  # type: ignore[attr-defined]

    def running_jobs(self) -> int:
        try:
            assert self.pg
            with self.pg.connect() as conn:
                return int(conn.execute("SELECT count(*) FROM scrape_jobs WHERE status = 'running'").fetchone()[0])
        except Exception:  # noqa: BLE001
            return 0

    def quit_from_menu(self) -> None:
        n = self.running_jobs()
        if n and message_box(
            "Ada pencarian yang sedang berjalan.\nJika Anda keluar sekarang, pencarian dihentikan "
            "(hasil yang sudah terkumpul tetap tersimpan).\n\nTetap keluar?", 0x20, 4
        ) != 6:
            return
        threading.Thread(target=self._quit, daemon=True).start()

    def _quit(self) -> None:
        self.tip("menutup…")
        self.shutdown()
        if self.icon is not None:
            self.icon.stop()

    def shutdown(self) -> None:
        if self.stopping.is_set():
            return
        self.stopping.set()
        self.log("shutdown dimulai")
        try:
            self.worker_stop_file.write_text("1")  # worker mengakhiri job berjalan dengan rapi
        except OSError:
            pass
        if self.worker:
            self.worker.stop(timeout=40)
        if self.api:
            self.api.stop(timeout=0)
        if self.pg:
            self.pg.stop()
        release_aliases()
        for f in (self.worker_stop_file, self.stop_file, self.pids_file):
            f.unlink(missing_ok=True)
        self.log("shutdown selesai")

    def run_tray(self) -> None:
        import pystray
        from PIL import Image

        try:
            with Image.open(self.layout.icon) as im:
                image = im.copy()  # lepaskan berkas: berkas terbuka menghalangi installer menimpanya saat pembaruan
        except Exception:  # noqa: BLE001
            image = Image.new("RGB", (64, 64), (79, 70, 229))
        menu = pystray.Menu(
            pystray.MenuItem("Buka Peta Toko", lambda: self.ready.is_set() and self.open_window(), default=True),
            pystray.MenuItem("Buka folder data", lambda: self.open_folder(self.layout.data)),
            pystray.MenuItem("Lihat log", lambda: self.open_folder(self.layout.logs)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Keluar", lambda: self.quit_from_menu()),
        )
        self.icon = pystray.Icon("PetaToko", image, f"{TITLE} - memulai…", menu)

        def on_ready(icon):
            icon.visible = True
            threading.Thread(target=self.boot, daemon=True).start()

        self.icon.run(setup=on_ready)


def _tail(path: Path, n: int = 12) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


# ---------------------------------------------------------------- perintah --stop
def stop_running(layout: Layout, wait: float = 90) -> int:
    """Minta instance yang sedang berjalan berhenti; bila macet paksa matikan. Dipakai installer."""
    pids_file = layout.run / "pids.json"
    pids = {}
    try:
        pids = json.loads(pids_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    launcher_pid = int(pids.get("launcher", 0) or 0)
    if launcher_pid and pid_alive(launcher_pid):
        layout.run.mkdir(parents=True, exist_ok=True)
        (layout.run / "launcher.stop").write_text("1")
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and pid_alive(launcher_pid):
            time.sleep(0.5)
    for key in ("launcher", "api", "worker"):  # sisa yang membandel
        pid = int(pids.get(key, 0) or 0)
        if pid and pid_alive(pid):
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    # pastikan database mati juga
    try:
        cfg = config.load(layout)
        if cfg is not None and (layout.pgdata / "PG_VERSION").exists():
            Postgres(layout, cfg).stop()
            release_aliases()
    except Exception:  # noqa: BLE001
        pass
    for f in (layout.run / "launcher.stop", layout.run / "worker.stop", pids_file):
        f.unlink(missing_ok=True)
    return 0


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Peluncur Peta Toko")
    ap.add_argument("--stop", action="store_true", help="hentikan instance yang berjalan")
    ap.add_argument("--background", action="store_true", help="jangan buka jendela")
    args = ap.parse_args(argv)

    layout = Layout()
    layout.ensure_dirs()
    if sys.stdout is None or sys.stderr is None or not sys.stdout.isatty():
        log = open(layout.logs / "launcher.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    setup_logging("INFO")  # structlog harus dikonfigurasi SETELAH stdout dialihkan (pythonw: stdout awalnya None)

    if args.stop:
        return stop_running(layout)

    instance = SingleInstance(layout.data)
    if instance.already_running:
        cfg = config.load(layout)
        if cfg is not None and not args.background:
            # instance pertama mungkin masih memulai: tunggu server siap agar jendela tidak menampilkan halaman galat
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline and not server_is_healthy(cfg.app_url):
                time.sleep(1)
            open_app_window(layout, cfg.app_url)
        return 0

    app = App(layout, background=args.background)
    app.log(f"Peta Toko {APP_VERSION} mulai; app={layout.app} data={layout.data}")
    try:
        app.run_tray()
    except Exception:  # noqa: BLE001
        import traceback

        app.log("TRAY GAGAL:\n" + traceback.format_exc())
        message_box("Peta Toko gagal membuat ikon di area notifikasi. Lihat log di folder data.", 0x10)
        app.shutdown()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
