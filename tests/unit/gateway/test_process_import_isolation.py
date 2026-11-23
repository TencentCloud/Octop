"""Import-hygiene guard for the gateway process/media modules.

``octop_harness.backends.workspace`` transitively imports deepagents and
every langchain provider SDK, which cost ~15s cold on Windows. Both
``gateway/process/agent_resolve.py`` and ``gateway/media/ingress.py`` only
need its ``BackendWorkspace`` for annotations, so a fresh interpreter that
imports the light history/gateway modules must never load the heavy roots —
otherwise even ``from octop.infra.gateway.process.message_keys import …``
pays for the whole agent stack and slow hosts flake timeouts (this bit the
versioned-history subprocess tests).
"""

from __future__ import annotations

import subprocess
import sys

# Heavy agent-stack roots that must stay out of light import paths.
BANNED_ROOTS = (
    "deepagents",
    "langchain_anthropic",
    "langchain_community",
    "langchain_google_genai",
    "langchain_openai",
    "octop_harness",
)

SCRIPT = """
import sys

imports = {imports!r}
for name in imports:
    __import__(name)

roots = sorted({{m.split(".")[0] for m in sys.modules}})
banned = [m for m in roots if m.startswith({banned_roots!r})]
print(banned)
if banned:
    raise SystemExit(1)
"""


def _assert_light_imports(imports: list[str]) -> None:
    script = SCRIPT.format(imports=imports, banned_roots=BANNED_ROOTS)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"light imports {imports} loaded banned roots {result.stdout.strip()}: {result.stderr}"
    )


def test_history_recorder_import_stays_light() -> None:
    """The history recording path must not pull the agent/provider stack."""
    _assert_light_imports(
        [
            "octop.infra.db.repos.thread_messages",
            "octop.infra.history.recorder",
            "octop.infra.history.service",
        ]
    )


def test_agent_resolve_and_media_ingress_import_stay_light() -> None:
    """Annotation-only uses of BackendWorkspace must not import it eagerly."""
    _assert_light_imports(
        [
            "octop.infra.gateway.media.ingress",
            "octop.infra.gateway.process.agent_resolve",
            "octop.infra.gateway.process.message_keys",
        ]
    )
