"""ACL gate coverage: no current_admin; known permission keys only."""

from __future__ import annotations

import ast
import pathlib

from octop.infra.users.permissions import ALL_PERMISSION_KEYS

API_ROOT = pathlib.Path("src/octop/api")

GATED_FILES = [
    "routers/users.py",
    "routers/admin.py",
    "routers/backup.py",
    "routers/security.py",
    "routers/providers.py",
    "routers/voice.py",
    "routers/storage_backends.py",
    "routers/envs.py",
    "routers/observability.py",
    "routers/tls.py",
    "routers/auth_oidc.py",
    "routers/update.py",
    "routers/search.py",
    "routers/ollama_models.py",
    "routers/onnx_models.py",
    "routers/connectors.py",
    "routers/knowledge_bases.py",
    "routers/browser/uninstall.py",
    "routers/browser/env.py",
    "routers/desktop/install.py",
    "routers/desktop/uninstall.py",
    "routers/desktop/status.py",
    "routers/desktop/settings.py",
    "routers/plugins.py",
    "routers/agents.py",
    "routers/channels.py",
    "routers/skill_packages.py",
    "routers/terminal.py",
    "routers/acp.py",
]


def test_no_current_admin_symbol_remains() -> None:
    hits: list[str] = []
    for path in API_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "current_admin":
                hits.append(str(path))
    assert not hits, f"current_admin still referenced in: {hits}"


def test_gated_files_call_require_permission_with_known_keys() -> None:
    for rel in GATED_FILES:
        src = (API_ROOT / rel).read_text(encoding="utf-8")
        assert "current_admin" not in src
        assert (
            "require_permission(" in src or "user_has_permission(" in src or "require_admin(" in src
        )
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require_permission"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                assert node.args[0].value in ALL_PERMISSION_KEYS, (
                    f"{rel}: unknown key {node.args[0].value!r}"
                )


def test_as_user_still_requires_admin() -> None:
    """Cross-user impersonation must not become a module permission."""
    agent = (API_ROOT / "common/agent.py").read_text(encoding="utf-8")
    usage = (API_ROOT / "routers/usage.py").read_text(encoding="utf-8")
    assert "as_user requires admin" in agent or "is_admin" in agent
    assert "as_user" in usage
