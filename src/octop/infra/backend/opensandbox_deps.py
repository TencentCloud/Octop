"""On-demand install of the official ``opensandbox`` SDK."""

from __future__ import annotations

import importlib.util

from octop.infra.utils.runtime_packages import PackageInstallSpec, install_packages

_OPENSANDBOX_SPEC = PackageInstallSpec(packages=("opensandbox>=0.1.16,<0.2",))


def opensandbox_sdk_available() -> bool:
    return importlib.util.find_spec("opensandbox") is not None


def ensure_opensandbox_deps(*, allow_install: bool = True) -> str:
    """Ensure the OpenSandbox SDK can be imported.

    Admin enable / probe / agent start pass ``allow_install=True``. Returns
    ``\"ready\"`` or ``\"installed\"``.
    """
    if opensandbox_sdk_available():
        return "ready"
    if not allow_install:
        raise RuntimeError(
            "OpenSandbox SDK is not installed. Enable this backend to install it automatically."
        )
    outcome = install_packages(
        _OPENSANDBOX_SPEC,
        is_satisfied=opensandbox_sdk_available,
        import_modules=("opensandbox",),
    )
    if not opensandbox_sdk_available():
        raise RuntimeError(
            "OpenSandbox SDK was installed but could not be loaded. Restart the server and try again."
        )
    return outcome
