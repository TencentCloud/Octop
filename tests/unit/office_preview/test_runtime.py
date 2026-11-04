from __future__ import annotations

from pathlib import Path

from octop.infra.office_preview.runtime import probe_runtime
from octop.infra.utils.paths import PathLayout


def test_probe_missing_node(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OCTOP_OFFICE_PREVIEW_NODE", raising=False)
    monkeypatch.delenv("OCTOP_OFFICE_PREVIEW_RUNTIME", raising=False)
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr("octop.infra.office_preview.runtime.shutil.which", lambda _name: None)
    probe = probe_runtime(PathLayout(tmp_path))
    assert probe.available is False
    assert probe.reason == "node_missing"


def test_probe_ok_when_helper_and_kit_present(monkeypatch, tmp_path: Path) -> None:
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\n", encoding="utf-8")
    helper = tmp_path / "office-preview"
    kit = helper / "node_modules" / "@deepseek-ai" / "libreoffice-kit"
    kit.mkdir(parents=True)
    (helper / ".kit-version").write_text("0.2.3", encoding="ascii")
    (helper / "convert.mjs").write_text("export {}\n", encoding="utf-8")
    monkeypatch.setenv("OCTOP_OFFICE_PREVIEW_NODE", str(node))
    monkeypatch.setenv("OCTOP_OFFICE_PREVIEW_RUNTIME", str(helper))

    def fake_run(args, **_kwargs):  # type: ignore[no-untyped-def]
        class _Proc:
            returncode = 0
            stdout = "v22.19.0\n"
            stderr = ""

        assert args[0] == str(node)
        return _Proc()

    monkeypatch.setattr("octop.infra.office_preview.runtime.subprocess.run", fake_run)
    probe = probe_runtime(PathLayout(tmp_path))
    assert probe.available is True
    assert probe.reason == "ok"


def test_probe_rejects_partial_install(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from octop.infra.office_preview import runtime

    helper = tmp_path / "office-preview"
    (helper / "node_modules" / "@deepseek-ai" / "libreoffice-kit").mkdir(parents=True)
    (helper / "convert.mjs").write_text("export {}", encoding="utf-8")
    monkeypatch.setenv("OCTOP_OFFICE_PREVIEW_RUNTIME", str(helper))
    monkeypatch.setattr(runtime, "resolve_node_bin", lambda: "node")
    monkeypatch.setattr(runtime, "_node_version_string", lambda _node: "v22.19.0")
    assert probe_runtime(PathLayout(tmp_path)).reason == "kit_missing"
