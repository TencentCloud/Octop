"""Profile management for browser session persistence."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from octop_browser.settings import settings as _settings

if TYPE_CHECKING:
    from octop_browser.settings import OctopSettings

logger = logging.getLogger(__name__)

# State file inside the profile dir that pins the page-level CDP target the
# *previous* octop-browser session attached to. CLI invocations are
# short-lived (one process per command) so without this file each new process
# would attach to whatever target Chrome happens to list first — which can be
# a stale ``about:blank`` tab rather than the one the user was driving.
_TARGET_STATE_FILE = ".octop-browser-target.json"
_PROFILE_PORTS_FILE = ".octop-browser-profiles.json"

# Older alternate filenames, read as a fallback so an existing profile keeps
# its port assignment and target binding instead of re-attaching to a random tab.
_LEGACY_TARGET_STATE_FILE = ".harness-browser-target.json"
_LEGACY_PROFILE_PORTS_FILE = ".harness-browser-profiles.json"


@dataclass
class Profile:
    """A named browser profile backed by a Chrome user-data-dir."""

    name: str
    data_dir: Path
    cdp_port: int

    # ------------------------------------------------------------------
    # Cross-process target stickiness
    # ------------------------------------------------------------------

    @property
    def _target_state_path(self) -> Path:
        return self.data_dir / _TARGET_STATE_FILE

    def load_target(self) -> str | None:
        """Return the cached page-level CDP target id, or ``None``.

        Used by :func:`octop_browser.cdp.launcher.get_page_ws_url` to
        re-attach to the same tab across CLI invocations.
        """
        path = self._target_state_path
        if not path.is_file():
            legacy = self.data_dir / _LEGACY_TARGET_STATE_FILE
            if not legacy.is_file():
                return None
            path = legacy
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Could not read %s: %s", path, exc)
            return None
        target_id = payload.get("target_id")
        return target_id if isinstance(target_id, str) and target_id else None

    def save_target(self, target_id: str) -> None:
        """Persist the active page-level target id.

        Best-effort: any I/O error is swallowed (next attach falls back to
        the heuristic in ``get_page_ws_url``).
        """
        if not target_id:
            return
        path = self._target_state_path
        try:
            path.write_text(
                json.dumps({"target_id": target_id}),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.debug("Could not write %s: %s", path, exc)

    def clear_target(self) -> None:
        """Forget the cached target id (best-effort)."""
        path = self._target_state_path
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.debug("Could not unlink %s: %s", path, exc)


class ProfileManager:
    """Creates and tracks browser profiles with stable CDP ports."""

    def __init__(
        self,
        base_dir: Path | None = None,
        settings: OctopSettings | None = None,
    ) -> None:
        """Create a manager.

        Args:
            base_dir: Root for profile user-data-dirs. Defaults to
                ``settings.profiles_dir``.
            settings: Settings used for port allocation. Defaults to the
                process-wide singleton. Pass an explicit object to keep a
                manager fully independent of the ambient environment —
                otherwise ``cdp_port_start`` would still come from the global
                settings even when ``base_dir`` is overridden.
        """
        cfg = settings or _settings
        self._settings = cfg
        self._base_dir = base_dir if base_dir is not None else cfg.profiles_dir
        self._profiles: dict[str, Profile] = {}

    @property
    def _ports_path(self) -> Path:
        return self._base_dir / _PROFILE_PORTS_FILE

    def _load_ports(self) -> dict[str, int]:
        path = self._ports_path
        if not path.is_file():
            legacy = self._base_dir / _LEGACY_PROFILE_PORTS_FILE
            if not legacy.is_file():
                return {}
            path = legacy
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Could not read %s: %s", path, exc)
            return {}
        if not isinstance(payload, dict):
            return {}
        ports: dict[str, int] = {}
        for key, value in payload.items():
            if isinstance(key, str) and isinstance(value, int):
                ports[key] = value
        return ports

    def _save_ports(self, ports: dict[str, int]) -> None:
        path = self._ports_path
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ports, sort_keys=True), encoding="utf-8")
        except OSError as exc:
            logger.debug("Could not write %s: %s", path, exc)

    def _assign_port(self, name: str) -> int:
        ports = self._load_ports()
        existing = ports.get(name)
        if existing is not None:
            return existing

        used_ports = set(ports.values()) | {p.cdp_port for p in self._profiles.values()}
        port = self._settings.cdp_port_start
        while port in used_ports:
            port += 1
        ports[name] = port
        self._save_ports(ports)
        return port

    def get_or_create(self, name: str) -> Profile:
        """Return an existing profile or create a new one."""
        if name in self._profiles:
            return self._profiles[name]
        data_dir = self._base_dir / name
        data_dir.mkdir(parents=True, exist_ok=True)
        port = self._assign_port(name)
        profile = Profile(name=name, data_dir=data_dir, cdp_port=port)
        self._profiles[name] = profile
        return profile

    def list_profiles(self) -> list[Profile]:
        """Return all known profiles."""
        return list(self._profiles.values())

    def delete(self, name: str) -> None:
        """Remove a profile and its data directory."""
        if name not in self._profiles:
            return
        profile = self._profiles.pop(name)
        ports = self._load_ports()
        if name in ports:
            ports.pop(name, None)
            self._save_ports(ports)
        if profile.data_dir.exists():
            shutil.rmtree(profile.data_dir)
