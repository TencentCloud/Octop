"""Green portable entry: wire packages/ onto sys.path then run ``octop``.

Using plain ``PYTHONPATH=packages`` skips ``.pth`` processing (pywin32 etc.).
``site.addsitedir`` loads those hooks. On Windows we also expose
``pywin32_system32`` DLLs so ``import pywintypes`` works.
"""

from __future__ import annotations

import contextlib
import os
import runpy
import site
import sys
from pathlib import Path


def _bootstrap() -> Path:
    root = Path(__file__).resolve().parent
    # The bundled interpreter is launched by absolute path, so its bin dir is
    # rarely on PATH. Prepend it so inherited envs (agent shells, subprocesses)
    # resolve ``python3`` to the same interpreter Octop runs with.
    interpreter_dir = os.path.dirname(sys.executable)
    if interpreter_dir:
        _path = os.environ.get("PATH", "")
        if interpreter_dir not in _path.split(os.pathsep):
            os.environ["PATH"] = (
                f"{interpreter_dir}{os.pathsep}{_path}" if _path else interpreter_dir
            )
    packages = root / "packages"
    if not packages.is_dir():
        sys.stderr.write(f"launch.py: packages/ missing next to {root}\n")
        raise SystemExit(1)

    # Process .pth files (required for pywin32 layout).
    site.addsitedir(str(packages))

    if sys.platform == "win32":
        dll_dir = packages / "pywin32_system32"
        if dll_dir.is_dir():
            dll_s = str(dll_dir)
            path = os.environ.get("PATH", "")
            if dll_s.lower() not in path.lower():
                os.environ["PATH"] = dll_s + os.pathsep + path
            # Python 3.8+: prefer explicit DLL search path.
            add_dll = getattr(os, "add_dll_directory", None)
            if add_dll is not None:
                with contextlib.suppress(OSError):
                    add_dll(dll_s)
    return root


def main() -> None:
    _bootstrap()
    # ``python launch.py …`` → same as ``python -m octop …``
    sys.argv = [sys.argv[0], *sys.argv[1:]]
    runpy.run_module("octop", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
