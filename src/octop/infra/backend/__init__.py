"""Agent backend configuration — Octop DB rows → harness specs + probes.

- :mod:`adapter` — ``storage_backends`` row → harness spec (no I/O)
- :mod:`resolver` — agent config ``named`` / ``composite`` expansion
- :mod:`probe` — admin connectivity checks (delegates round-trip to harness-agent)
"""

from octop.infra.backend.adapter import row_to_backend_spec
from octop.infra.backend.probe import probe_storage_backend
from octop.infra.backend.resolver import default_agent_backend_spec, resolve_agent_backend_spec
from octop.infra.backend.windows_execute import apply as _apply_windows_execute_patch

# Windows: make agent local_shell ``execute`` tolerate native GBK/CP936
# subprocess output (deepagents reads text pipes as strict UTF-8 and drops the
# whole result on the first non-UTF-8 byte) and stop the harness virtual-path
# rewrite from mangling ``C:\…`` / ``C:/…`` drive paths. Applied at import so
# every backend built afterwards runs the patched implementation.
_apply_windows_execute_patch()

__all__ = [
    "default_agent_backend_spec",
    "probe_storage_backend",
    "resolve_agent_backend_spec",
    "row_to_backend_spec",
]
