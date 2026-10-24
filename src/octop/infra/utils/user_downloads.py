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

# Per-component filename limit budget (UTF-8 bytes). 200 bytes stays under the
# 255 UTF-16 code-unit limit on Windows and the 255-byte limit on Unix
# filesystems, and leaves room for the numbered collision suffix "(999)".
_NAME_BYTE_BUDGET = 200
# An extension longer than this is unlikely to be a real extension; treat the
# trailing dot as part of the stem instead of splitting it off.
_MAX_SUFFIX_CHARS = 11


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


def _truncate_to_bytes(text: str, budget: int) -> str:
    """Return *text* with its UTF-8 encoding capped at *budget* bytes.

    Never splits a multi-byte character: the trailing incomplete byte
    sequence is dropped, leaving a valid string on a character boundary.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= budget:
        return text
    decoded = encoded[:budget].decode("utf-8", errors="ignore")
    return decoded or text[:1]


def sanitize_download_filename(raw: str | None) -> str:
    name = _UNSAFE_NAME.sub("_", (raw or "").strip()) or "download"
    name = name.lstrip(".")
    if name in {"", ".", ".."}:
        return "download"
    if len(name.encode("utf-8")) <= _NAME_BYTE_BUDGET:
        return name
    # Bound by encoded byte length instead of character count so that long
    # non-ASCII names (CJK, emoji) stay under the 255 UTF-16 (Windows) /
    # 255-byte (Unix) per-component filesystem limit that ``name[:200]`` missed.
    dot = name.rfind(".")
    if dot > 0 and (len(name) - dot) <= _MAX_SUFFIX_CHARS:
        stem, suffix = name[:dot], name[dot:]
    else:
        stem, suffix = name, ""
    suffix_len = len(suffix.encode("utf-8"))
    stem_budget = _NAME_BYTE_BUDGET - suffix_len
    if stem_budget < 1:
        # The extension alone exceeds the budget; fall back to a whole-name
        # truncation so we still honour the byte cap.
        return _truncate_to_bytes(name, _NAME_BYTE_BUDGET)
    truncated_stem = _truncate_to_bytes(stem, stem_budget)
    if not truncated_stem:
        truncated_stem = "download"
    return truncated_stem + suffix


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
