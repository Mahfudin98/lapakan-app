"""Konfigurasi edisi desktop (config.json di folder data): port dan kata sandi database."""
import json
import os
import secrets
import socket
import tempfile
from dataclasses import asdict, dataclass
from urllib.parse import quote

from app.desktop.paths import Layout

DEFAULT_PG_PORT = 54329  # sengaja bukan 5432 agar tidak bentrok dengan PostgreSQL lain di komputer pengguna
DEFAULT_APP_PORT = 8765


class ConfigError(RuntimeError):
    pass


@dataclass
class DesktopConfig:
    pg_port: int
    app_port: int
    db_password: str
    db_user: str = "petatoko"
    db_name: str = "petatoko"
    version: int = 1

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{quote(self.db_user, safe='')}:{quote(self.db_password, safe='')}"
            f"@127.0.0.1:{self.pg_port}/{self.db_name}"
        )

    @property
    def app_url(self) -> str:
        return f"http://127.0.0.1:{self.app_port}/"


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def find_free_port(preferred: int, avoid: tuple[int, ...] = ()) -> int:
    for port in range(preferred, preferred + 200):
        if port not in avoid and port_is_free(port):
            return port
    raise ConfigError(f"tidak ada port kosong di sekitar {preferred}")


def new_config() -> DesktopConfig:
    pg = find_free_port(DEFAULT_PG_PORT)
    app = find_free_port(DEFAULT_APP_PORT, avoid=(pg,))
    return DesktopConfig(pg_port=pg, app_port=app, db_password=secrets.token_urlsafe(24))


def load(layout: Layout) -> DesktopConfig | None:
    """None bila belum ada. ConfigError bila berkas ada tetapi rusak (jangan ditimpa diam-diam:
    kata sandi database ada di dalamnya)."""
    f = layout.config_file
    if not f.exists():
        return None
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
        return DesktopConfig(
            pg_port=int(raw["pg_port"]), app_port=int(raw["app_port"]), db_password=str(raw["db_password"]),
            db_user=str(raw.get("db_user", "petatoko")), db_name=str(raw.get("db_name", "petatoko")),
            version=int(raw.get("version", 1)),
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise ConfigError(f"config.json rusak ({exc}): {f}") from exc


def save(layout: Layout, cfg: DesktopConfig) -> None:
    """Tulis atomik: tidak pernah meninggalkan berkas setengah jadi bila listrik padam."""
    layout.data.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=layout.data, prefix="config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(cfg), fh, indent=2)
        os.replace(tmp, layout.config_file)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
