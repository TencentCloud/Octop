"""Harness wrappers around deepagents ``CompositeBackend``."""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import CompositeBackend


class MountedCompositeBackend(CompositeBackend):
    """``CompositeBackend`` that exposes the default backend's local mount as ``cwd``.

    deepagents ``CompositeBackend`` has no ``cwd`` / ``root_dir``. Harness
    :class:`~octop_harness.backends.workspace.BackendWorkspace` discovers a
    local mount via those attributes for ``mkdir`` / ``move`` / ``delete``.
    Without them, workspace mutations raise
    :class:`~octop_harness.backends.utils.BackendOperationNotSupportedError`
    even when the default backend is a local filesystem or shell backend.
    """

    @property
    def cwd(self) -> Path | None:
        mount = getattr(self.default, "cwd", None) or getattr(self.default, "root_dir", None)
        if mount is None:
            return None
        return Path(mount)

    @property
    def root_dir(self) -> Path | None:
        """Alias of :attr:`cwd` for callers that prefer ``root_dir``."""
        return self.cwd

    @property
    def virtual_mode(self) -> bool:
        """Mirror the default backend so path helpers see virtual semantics."""
        return getattr(self.default, "virtual_mode", False) is True

    def _resolve_path(self, key: str) -> Path:
        resolve_fn = getattr(self.default, "_resolve_path", None)
        if callable(resolve_fn):
            return Path(resolve_fn(key))
        cwd = self.cwd
        if cwd is None:
            msg = "MountedCompositeBackend has no local mount for path resolve"
            raise RuntimeError(msg)
        return (cwd / str(key).lstrip("/")).resolve()


__all__ = ["MountedCompositeBackend"]
