"""Mencari browser yang sudah terpasang (Microsoft Edge / Google Chrome) di Windows."""
import os
import sys
from pathlib import Path


def _registry_app_path(exe: str) -> Path | None:
    if sys.platform != "win32":
        return None
    import winreg

    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                value, _ = winreg.QueryValueEx(k, "")
                p = Path(value.strip('"'))
                if p.exists():
                    return p
        except OSError:
            continue
    return None


def _candidates(*parts: str) -> list[Path]:
    out = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            out.append(Path(base, *parts))
    return out


def find_edge() -> Path | None:
    for p in _candidates("Microsoft", "Edge", "Application", "msedge.exe"):
        if p.exists():
            return p
    return _registry_app_path("msedge.exe")


def find_chrome() -> Path | None:
    for p in _candidates("Google", "Chrome", "Application", "chrome.exe"):
        if p.exists():
            return p
    return _registry_app_path("chrome.exe")


def find_any() -> Path | None:
    return find_edge() or find_chrome()
