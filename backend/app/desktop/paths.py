"""Lokasi berkas edisi desktop.

- app_dir  : folder instalasi (read-only saat dipakai): runtime Python, backend, frontend, pgsql.
- data_dir : data pengguna (database, log, konfigurasi). Tidak ikut terhapus saat update aplikasi.
"""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def ansi_safe(text: str) -> bool:
    """True bila teks dapat diteruskan apa adanya lewat API ANSI Windows (codepage sistem)."""
    if sys.platform != "win32":
        return True
    try:
        return text.encode("mbcs").decode("mbcs") == text
    except UnicodeError:
        return False


_created_aliases: list[tuple[str, str]] = []  # (huruf drive, target) yang dibuat oleh proses ini


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.DefineDosDeviceW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR]
    k.DefineDosDeviceW.restype = wintypes.BOOL
    k.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    k.QueryDosDeviceW.restype = wintypes.DWORD
    k.GetLogicalDrives.restype = wintypes.DWORD
    return k


def ascii_alias(path: Path) -> Path:
    """Path yang aman dipakai PostgreSQL.

    PostgreSQL di Windows menerima argumen baris perintah dalam codepage ANSI, sehingga folder bernama non-Latin
    (di luar codepage sistem) tidak dapat dipakai langsung. Untuk path seperti itu, folder dipetakan ke sebuah huruf
    drive (seperti `subst`, tanpa hak admin) dan path berbasis huruf itu yang diberikan ke PostgreSQL.
    (Directory junction TIDAK dipakai: Windows terbaru menolak melintasi junction buatan pengguna biasa dengan
    galat 448 'untrusted mount point' - RedirectionGuard.) Path yang sudah aman dikembalikan apa adanya.
    Panggil release_aliases() setelah PostgreSQL dimatikan."""
    if ansi_safe(str(path)):
        return path
    import ctypes

    k = _kernel32()
    target = str(path).rstrip("\\")
    want = ("\\??\\" + target).lower()
    used = k.GetLogicalDrives()
    for i in range(26):  # pakai ulang pemetaan yang sudah ada ke folder yang sama
        if used & (1 << i):
            letter = f"{chr(65 + i)}:"
            buf = ctypes.create_unicode_buffer(1024)
            if k.QueryDosDeviceW(letter, buf, 1024) and buf.value.lower() == want:
                return Path(letter + "\\")
    for i in range(25, 2, -1):  # Z ... D
        if not used & (1 << i):
            letter = f"{chr(65 + i)}:"
            if not k.DefineDosDeviceW(0, letter, target):
                raise OSError(f"DefineDosDevice gagal (kode {ctypes.get_last_error()})")
            _created_aliases.append((letter, target))
            return Path(letter + "\\")
    raise OSError("tidak ada huruf drive yang kosong")


def release_aliases() -> None:
    """Lepaskan pemetaan drive yang dibuat proses ini (aman dipanggil berulang)."""
    if not _created_aliases:
        return
    k = _kernel32()
    for letter, target in _created_aliases:
        k.DefineDosDeviceW(2 | 4, letter, target)  # REMOVE_DEFINITION | EXACT_MATCH_ON_REMOVE
    _created_aliases.clear()


def default_app_dir() -> Path:
    env = os.environ.get("PETATOKO_HOME")
    if env:
        return Path(env)
    # .../<app>/backend/app/desktop/paths.py -> <app>
    return Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    env = os.environ.get("PETATOKO_DATA")
    if env:
        return Path(env)
    # lokasi data pilihan pengguna saat instalasi (ditulis installer di folder aplikasi)
    pointer = default_app_dir() / "data-location.txt"
    try:
        raw = pointer.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:  # berkas ANSI dari versi lama / editor lain
            text = raw.decode("cp1252", errors="replace")
        text = text.strip().splitlines()[0].strip() if text.strip() else ""
        if text:
            return Path(text)
    except OSError:
        pass
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "PetaToko"


@dataclass(frozen=True)
class Layout:
    app: Path = field(default_factory=default_app_dir)
    data: Path = field(default_factory=default_data_dir)

    # --- komponen aplikasi ---
    @property
    def pg_bin(self) -> Path:
        return self.app / "pgsql" / "bin"

    @property
    def backend(self) -> Path:
        return self.app / "backend"

    @property
    def static(self) -> Path:
        return self.app / "frontend" / "dist"

    @property
    def icon(self) -> Path:
        return self.app / "assets" / "petatoko.ico"

    @property
    def python(self) -> Path:
        """Interpreter untuk proses anak (console; dijalankan tanpa jendela)."""
        embedded = self.app / "runtime" / "python.exe"
        return embedded if embedded.exists() else Path(sys.executable)

    @property
    def seed_regions(self) -> Path:
        return self.backend / "app" / "desktop" / "data" / "regions.csv.gz"

    # --- data pengguna ---
    @property
    def pgdata(self) -> Path:
        return self.data / "pgdata"

    @property
    def logs(self) -> Path:
        return self.data / "logs"

    @property
    def debug(self) -> Path:
        return self.data / "debug"

    @property
    def run(self) -> Path:
        return self.data / "run"

    @property
    def browsers(self) -> Path:
        return self.data / "browsers"

    @property
    def browser_profile(self) -> Path:
        return self.data / "browser-profile"

    @property
    def config_file(self) -> Path:
        return self.data / "config.json"

    @property
    def setup_marker(self) -> Path:
        return self.data / "setup.json"

    def ensure_dirs(self) -> None:
        for d in (self.data, self.logs, self.debug, self.run):
            d.mkdir(parents=True, exist_ok=True)
