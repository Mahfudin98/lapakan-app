"""Tes edisi desktop (Windows). Sebagian besar murni logika dan berjalan di mana pun; yang spesifik Windows di-skip di OS lain."""
import asyncio
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.desktop import browser, config, setup
from app.desktop.launcher import Child, SingleInstance, pid_alive, stop_running
from app.desktop.paths import Layout, default_data_dir
from app.desktop.postgres import Postgres, PostgresError

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="khusus Windows")


@pytest.fixture
def layout(tmp_path, monkeypatch):
    monkeypatch.delenv("PETATOKO_DATA", raising=False)
    monkeypatch.setenv("PETATOKO_HOME", str(tmp_path / "app dir"))
    (tmp_path / "app dir").mkdir()
    lay = Layout(app=tmp_path / "app dir", data=tmp_path / "data dir")
    lay.ensure_dirs()
    return lay


# --- paths ------------------------------------------------------------------------------------
def test_data_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PETATOKO_DATA", str(tmp_path / "x"))
    assert default_data_dir() == tmp_path / "x"


def test_data_dir_from_installer_pointer_file(monkeypatch, tmp_path):
    monkeypatch.delenv("PETATOKO_DATA", raising=False)
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setenv("PETATOKO_HOME", str(app))
    (app / "data-location.txt").write_text("\ufeffD:\\Data Saya\\PetaToko\r\n", encoding="utf-8")  # BOM + CRLF dari Inno
    assert default_data_dir() == Path("D:\\Data Saya\\PetaToko")


def test_data_dir_defaults_to_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("PETATOKO_DATA", raising=False)
    monkeypatch.setenv("PETATOKO_HOME", str(tmp_path / "kosong"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert default_data_dir() == tmp_path / "local" / "PetaToko"


def test_layout_component_paths(layout):
    assert layout.pg_bin == layout.app / "pgsql" / "bin"
    assert layout.static == layout.app / "frontend" / "dist"
    assert layout.seed_regions.name == "regions.csv.gz"
    assert layout.logs.is_dir() and layout.run.is_dir()


# --- config -------------------------------------------------------------------------------------
def test_new_config_uses_distinct_free_ports():
    cfg = config.new_config()
    assert cfg.pg_port != cfg.app_port
    assert config.port_is_free(cfg.pg_port) and config.port_is_free(cfg.app_port)
    assert len(cfg.db_password) >= 24


def test_find_free_port_skips_occupied_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        busy = s.getsockname()[1]
        assert not config.port_is_free(busy)
        assert config.find_free_port(busy) != busy


def test_config_roundtrip_and_no_temp_files_left(layout):
    cfg = config.new_config()
    config.save(layout, cfg)
    assert config.load(layout) == cfg
    assert [p.name for p in layout.data.glob("config.*") if p.suffix == ".tmp"] == []


def test_config_missing_returns_none_but_corrupt_raises_and_is_kept(layout):
    assert config.load(layout) is None
    layout.config_file.write_text("{ bukan json", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(layout)
    assert layout.config_file.read_text(encoding="utf-8") == "{ bukan json"  # tidak ditimpa diam-diam


@pytest.mark.parametrize("password", ["biasa", "p@ss/w:rd%40#?&=+ ", "üñíçødé", "a" * 200])
def test_database_url_survives_special_characters(password):
    cfg = config.DesktopConfig(pg_port=54329, app_port=8765, db_password=password)
    url = make_url(cfg.database_url)
    assert url.password == password
    assert (url.host, url.port, url.username, url.database) == ("127.0.0.1", 54329, "petatoko", "petatoko")


# --- browser ----------------------------------------------------------------------------------------
def test_find_edge_in_program_files(monkeypatch, tmp_path):
    exe = tmp_path / "pf86" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "none"))
    assert browser.find_edge() == exe or sys.platform == "win32"  # di Windows registry dapat menjawab lebih dulu
    assert browser.find_any() is not None or sys.platform != "win32"


def test_find_chrome_in_localappdata(monkeypatch, tmp_path):
    exe = tmp_path / "local" / "Google" / "Chrome" / "Application" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    assert browser.find_chrome() is not None


@windows_only
def test_this_windows_machine_has_a_browser():
    assert browser.find_any() is not None


# --- postgres (tanpa biner) -----------------------------------------------------------------------------
def test_running_port_parses_postmaster_pid(layout, monkeypatch):
    cfg = config.DesktopConfig(pg_port=54329, app_port=8765, db_password="x")
    pg = Postgres(layout, cfg)
    layout.pgdata.mkdir(parents=True)
    (layout.pgdata / "postmaster.pid").write_text("1234\nD:/data\n1700000000\n54555\n\n127.0.0.1\n", encoding="utf-8")
    monkeypatch.setattr(pg, "_exe", lambda name: name)
    monkeypatch.setattr(pg, "_run", lambda *a, **k: (0, ""))  # pg_ctl status: berjalan
    assert pg.running_port() == 54555
    monkeypatch.setattr(pg, "_run", lambda *a, **k: (3, ""))  # tidak berjalan
    assert pg.running_port() is None


def test_init_refuses_to_touch_unknown_non_empty_folder(layout):
    cfg = config.DesktopConfig(pg_port=54329, app_port=8765, db_password="x")
    layout.pgdata.mkdir(parents=True)
    (layout.pgdata / "milik-orang-lain.txt").write_text("jangan hapus", encoding="utf-8")
    with pytest.raises(PostgresError):
        Postgres(layout, cfg).init()
    assert (layout.pgdata / "milik-orang-lain.txt").exists()


def test_missing_postgres_binaries_give_clear_error(layout):
    cfg = config.DesktopConfig(pg_port=54329, app_port=8765, db_password="x")
    with pytest.raises(PostgresError, match="komponen database tidak ditemukan"):
        Postgres(layout, cfg).init()


# --- setup -------------------------------------------------------------------------------------------------
def test_setup_marker_logic(layout):
    assert setup.is_complete(layout) is False
    layout.setup_marker.write_text(json.dumps({"completed": True}), encoding="utf-8")
    assert setup.is_complete(layout) is False  # tanpa config dan database
    layout.config_file.write_text("{}", encoding="utf-8")
    layout.pgdata.mkdir(parents=True)
    (layout.pgdata / "PG_VERSION").write_text("16", encoding="utf-8")
    assert setup.is_complete(layout) is True
    layout.setup_marker.write_text("rusak", encoding="utf-8")
    assert setup.is_complete(layout) is False


def test_reporter_writes_progress_lines_for_the_installer(layout, tmp_path):
    pf = tmp_path / "progress.txt"
    rep = setup.Reporter(layout, pf)
    rep.step(2, "Menyiapkan folder data")
    rep.warn("peringatan")
    rep.error("gagal\ndua baris")
    rep.done()
    lines = pf.read_text(encoding="utf-8").splitlines()
    assert lines == [f"STEP|2|{setup.TOTAL_STEPS}|Menyiapkan folder data", "WARN|peringatan", "ERROR|gagal dua baris", "DONE"]
    assert "STEP|2" in (layout.logs / "setup.log").read_text(encoding="utf-8")


def test_setup_main_reports_error_when_app_files_missing(tmp_path, monkeypatch):
    home, data = tmp_path / "app kosong", tmp_path / "data setup"
    home.mkdir()
    monkeypatch.setenv("PETATOKO_HOME", str(home))
    monkeypatch.setenv("PETATOKO_DATA", str(data))
    pf = tmp_path / "p.txt"
    assert setup.main(["--progress-file", str(pf), "--skip-browser-download"]) == 1
    lines = pf.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("STEP|1|")
    assert lines[-1].startswith("ERROR|") and "berkas aplikasi tidak lengkap" in lines[-1]
    assert "Traceback" in (data / "logs" / "setup.log").read_text(encoding="utf-8")


# --- launcher ----------------------------------------------------------------------------------------------
@windows_only
def test_single_instance_mutex_detects_second_instance(tmp_path):
    first = SingleInstance(tmp_path / "data-a")
    assert first.already_running is False
    second = SingleInstance(tmp_path / "data-a")
    assert second.already_running is True
    other = SingleInstance(tmp_path / "data-b")  # folder data lain = instance lain yang sah
    assert other.already_running is False


@windows_only
def test_pid_alive():
    assert pid_alive(os.getpid()) is True
    assert pid_alive(0) is False
    assert pid_alive(2**31 - 1) is False


def test_child_restart_budget(tmp_path):
    child = Child("x", ["python"], {}, tmp_path, tmp_path / "x.log")
    for _ in range(4):
        child.starts.append(time.monotonic())
    assert child.can_restart() is True
    child.starts.append(time.monotonic())
    assert child.can_restart() is False  # 5 kali dalam 10 menit: berhenti memulai ulang
    child.starts = [time.monotonic() - 3600] * 9  # percobaan lama tidak dihitung
    assert child.can_restart() is True


def test_child_runs_and_logs_output(tmp_path):
    child = Child("echo", [sys.executable, "-c", "print('halo dari anak')"], dict(os.environ), tmp_path, tmp_path / "echo.log")
    child.start()
    child.proc.wait(30)
    assert "halo dari anak" in (tmp_path / "echo.log").read_text(encoding="utf-8")
    assert child.alive() is False


def test_stop_running_with_nothing_running_is_a_noop(layout):
    assert stop_running(layout, wait=1) == 0


# --- worker: berkas berhenti -----------------------------------------------------------------------------------
def test_worker_exits_when_stop_file_exists(monkeypatch, tmp_path):
    pytest.importorskip("psycopg")
    from app.config import get_settings

    url = make_url(get_settings().database_url)
    try:  # cek cepat: koneksi ke port mati di Windows bisa menunggu sangat lama
        socket.create_connection((url.host, url.port or 5432), timeout=2).close()
        from sqlalchemy import text

        from app.db import engine

        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception:
        pytest.skip("database tidak tersedia")
    from app.workers import runner

    stop_file = tmp_path / "worker.stop"
    stop_file.write_text("1")
    monkeypatch.setenv("PETATOKO_STOP_FILE", str(stop_file))
    saved = {n: signal.getsignal(getattr(signal, n)) for n in ("SIGINT", "SIGTERM") if hasattr(signal, n)}
    try:
        code = asyncio.run(asyncio.wait_for(runner.main(), timeout=60))
    finally:
        for name, handler in saved.items():
            signal.signal(getattr(signal, name), handler)
    assert code == 0


def test_data_location_pointer_accepts_utf8_ansi_and_extra_lines(monkeypatch, tmp_path):
    monkeypatch.delenv("PETATOKO_DATA", raising=False)
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setenv("PETATOKO_HOME", str(app))
    pointer = app / "data-location.txt"
    pointer.write_bytes(("\ufeff" + r"D:\Данные Тест\PetaToko" + "\r\nbaris lain").encode("utf-8"))  # UTF-8 + BOM (Inno)
    assert default_data_dir() == Path(r"D:\Данные Тест\PetaToko")
    pointer.write_bytes("D:\\Pengguna \xdcn\xefc\xf6de\\PetaToko".encode("cp1252"))  # ANSI lama: tidak boleh crash
    assert "PetaToko" in str(default_data_dir())


# --- path non-Latin: PostgreSQL di Windows hanya menerima argumen ANSI ---------------------------------------
def test_ansi_safe_accepts_normal_windows_paths():
    from app.desktop.paths import ansi_safe

    assert ansi_safe(r"C:\Users\Budi Santoso\AppData\Local\PetaToko")
    assert ansi_safe("D:\\Data \xdcn\xefc\xf6de")  # Latin-1 aman di codepage Barat


@windows_only
def test_ascii_alias_maps_non_ansi_folder_to_a_drive_letter(tmp_path):
    from app.desktop.paths import ansi_safe, ascii_alias, release_aliases

    cy = "".join(chr(c) for c in (0x414, 0x430, 0x43D, 0x43D, 0x44B, 0x435))  # "Данные"
    target = tmp_path / f"{cy} Saya"
    target.mkdir()
    (target / "x.txt").write_text("halo", encoding="utf-8")
    if ansi_safe(str(target)):
        pytest.skip("codepage sistem ini mendukung huruf Sirilik")
    alias = ascii_alias(target)
    try:
        assert ansi_safe(str(alias)) and len(str(alias)) == 3  # mis. "Z:\\"
        assert (alias / "x.txt").read_text(encoding="utf-8") == "halo"  # menunjuk ke folder yang sama
        (alias / "baru.txt").write_text("dari alias", encoding="utf-8")
        assert (target / "baru.txt").read_text(encoding="utf-8") == "dari alias"
        assert ascii_alias(target) == alias  # idempoten: memakai ulang pemetaan yang sama
    finally:
        release_aliases()
    assert not os.path.exists(str(alias))  # pemetaan dilepas
    assert (target / "x.txt").exists()  # data asli utuh


def test_ascii_alias_returns_safe_path_unchanged(tmp_path):
    from app.desktop.paths import ascii_alias

    assert ascii_alias(tmp_path) == tmp_path


def test_window_command_has_flags_that_prevent_edge_dialogs(tmp_path):
    from app.desktop.launcher import window_command

    cmd = window_command(Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"), "http://127.0.0.1:8765/", tmp_path / "profil browser")
    joined = " ".join(cmd)
    assert "--app=http://127.0.0.1:8765/" in cmd
    assert f"--user-data-dir={tmp_path / 'profil browser'}" in cmd  # path berspasi tetap satu argumen
    assert "--disable-sync" in cmd and "--lang=id" in cmd and "--no-first-run" in cmd
    assert "msImplicitSignin" in joined and "Translate" in joined
    assert sum(a.startswith("--disable-features=") for a in cmd) == 1  # beberapa flag yang sama saling menimpa


@windows_only
def test_process_image_and_pid_helpers():
    from app.desktop.launcher import process_image

    assert process_image(os.getpid()).lower().endswith(("python.exe", "pythonw.exe", "python3.exe", "python3.13.exe", "python3.12.exe")) or process_image(os.getpid())
    assert process_image(2**31 - 1) is None


def test_server_is_healthy_rejects_closed_port():
    from app.desktop.launcher import server_is_healthy

    assert server_is_healthy("http://127.0.0.1:9/") is False


def test_logging_works_when_stdout_was_none_at_import_time(tmp_path):
    """Regresi: peluncur Windows berjalan di pythonw (sys.stdout=None saat impor). structlog menangkap stdout saat
    impor, sehingga log pertama setelah stdout dialihkan melempar TypeError (terjadi pada penyembuhan otomatis)."""
    import subprocess

    out = tmp_path / "log.txt"
    code = (
        "import sys; sys.stdout = None; sys.stderr = None\n"  # seperti pythonw
        "import app.desktop.postgres as pg\n"  # mengimpor structlog saat stdout None
        f"f = open({str(out)!r}, 'w', encoding='utf-8', buffering=1); sys.stdout = sys.stderr = f\n"
        "from app.logging import setup_logging; setup_logging('INFO')\n"
        "pg.log.info('halo_dari_pythonw', data='x')\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "halo_dari_pythonw" in out.read_text(encoding="utf-8")


@windows_only
def test_stop_running_kills_a_stuck_launcher_recorded_in_pids_file(layout):
    """Regresi: peluncur yang macet (mis. menunggu dialog) harus tetap bisa dimatikan oleh `--stop` (installer)."""
    import subprocess

    stuck = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], creationflags=0x08000000)
    try:
        layout.run.mkdir(parents=True, exist_ok=True)
        (layout.run / "pids.json").write_text(json.dumps({"launcher": stuck.pid, "api": 0, "worker": 0}), encoding="utf-8")
        t0 = time.monotonic()
        assert stop_running(layout, wait=2) == 0
        stuck.wait(15)
        assert stuck.poll() is not None  # dimatikan paksa setelah batas tunggu
        assert time.monotonic() - t0 < 40
    finally:
        if stuck.poll() is None:
            stuck.kill()


@windows_only
def test_cleanup_orphans_reads_old_pids_before_new_launcher_pid_is_recorded(layout, tmp_path, monkeypatch):
    """Regresi: mencatat pid peluncur baru lebih dulu menimpa pids.json lama sehingga yatim tidak pernah dimatikan."""
    import subprocess

    import app.desktop.launcher as launcher

    exe = layout.app / "runtime" / "python.exe"  # milik "instalasi ini" menurut cek path
    exe.parent.mkdir(parents=True)
    exe.write_bytes(Path(sys.executable).read_bytes())
    orphan = subprocess.Popen([str(exe), "-c", "import time; time.sleep(120)"], creationflags=0x08000000)
    try:
        layout.run.mkdir(parents=True, exist_ok=True)
        (layout.run / "pids.json").write_text(json.dumps({"launcher": 1, "api": orphan.pid, "worker": 0}), encoding="utf-8")
        app = launcher.App(layout, background=True)
        app.cleanup_orphans()  # urutan di _boot: bersihkan dulu...
        app.write_pids()  # ...baru catat pid baru
        orphan.wait(20)
        assert orphan.poll() is not None
        assert json.loads((layout.run / "pids.json").read_text(encoding="utf-8"))["launcher"] == os.getpid()
    finally:
        if orphan.poll() is None:
            orphan.kill()


def test_launcher_boot_cleans_orphans_before_recording_pids():
    """Pengaman urutan pada kode _boot (bukan hanya pada pembantu)."""
    src = (Path(__file__).resolve().parents[1] / "app" / "desktop" / "launcher.py").read_text(encoding="utf-8")
    boot = src[src.index("def _boot"):src.index("def cleanup_orphans")]
    assert boot.index("self.cleanup_orphans()") < boot.index("self.write_pids()") < boot.index("setup.is_complete")
