"""Save a user-chosen file into the host Downloads folder."""

from __future__ import annotations

import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_UNSAFE_NAME = re.compile(r"[\\/:\0<>\"|?*]")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_loopback_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def request_hostname(host_header: str) -> str:
    raw = host_header.strip()
    if raw.startswith("["):
        end = raw.find("]")
        return raw[1:end].lower() if end > 0 else raw.lower()
    return raw.split(":", 1)[0].lower()


def is_local_dashboard_request(request: Any) -> bool:
    """True when the dashboard is talking to Octop on this machine.

    Requires a loopback peer *and* a loopback Host header so a local reverse
    proxy cannot turn this into a remote write-to-Downloads endpoint.
    """
    client = getattr(request, "client", None)
    peer = getattr(client, "host", "") if client is not None else ""
    if not is_loopback_address(str(peer or "")):
        return False
    headers = getattr(request, "headers", {})
    host = headers.get("host") if hasattr(headers, "get") else ""
    return request_hostname(str(host or "")) in _LOOPBACK_HOSTS


def sanitize_download_filename(raw: str | None) -> str:
    name = _UNSAFE_NAME.sub("_", (raw or "").strip()) or "download"
    name = name.lstrip(".")
    if name in {"", ".", ".."}:
        return "download"
    return name[:200]


def downloads_dir(*, home: Path | None = None) -> Path:
    root = Path.home() if home is None else home
    candidate = root / "Downloads"
    return candidate if candidate.is_dir() else root


def unique_download_path(filename: str, *, home: Path | None = None) -> Path:
    dest_dir = downloads_dir(home=home)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = sanitize_download_filename(filename)
    path = dest_dir / safe
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for index in range(1, 1000):
        candidate = dest_dir / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    return dest_dir / f"{stem}-{os.getpid()}{suffix}"


def save_user_download(
    filename: str,
    data: bytes,
    *,
    home: Path | None = None,
) -> Path:
    path = unique_download_path(filename, home=home)
    path.write_bytes(data)
    return path


def reveal_download(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["open", "-R", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif os.name == "nt":
            subprocess.Popen(
                ["explorer", f"/select,{path}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["xdg-open", str(path.parent)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError:
        return
