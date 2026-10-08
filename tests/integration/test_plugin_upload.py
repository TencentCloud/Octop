"""Integration tests for uploading a plugin ZIP from the dashboard."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "echo-tool"


def _echo_zip(plugin_id: str = "echo-tool") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path in _FIXTURE.rglob("*"):
            if path.is_file():
                arcname = f"echo-tool/{path.relative_to(_FIXTURE).as_posix()}"
                if path.name == "plugin.yaml":
                    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
                    manifest["id"] = plugin_id
                    zf.writestr(arcname, yaml.safe_dump(manifest))
                else:
                    zf.write(path, arcname=arcname)
    return buf.getvalue()


def _zip_files() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("echo-tool.zip", _echo_zip(), "application/zip")}


async def test_upload_plugin_zip_installs(env: Any) -> None:
    client, _srv, auth = env
    r = await client.post("/api/plugins/upload", files=_zip_files(), headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "echo-tool"
    assert body["kind"] == "tool"

    listing = (await client.get("/api/plugins", headers=auth)).json()
    assert any(p.get("id") == "echo-tool" for p in listing)


async def test_upload_plugin_overwrite_behavior(env: Any) -> None:
    client, _srv, auth = env
    # First install succeeds.
    r1 = await client.post(
        "/api/plugins/upload",
        files=_zip_files(),
        data={"force": "true"},
        headers=auth,
    )
    assert r1.status_code == 200, r1.text

    # Same id without force → conflict.
    r2 = await client.post("/api/plugins/upload", files=_zip_files(), headers=auth)
    assert r2.status_code == 409, r2.text

    # Same id with force → overwrites.
    r3 = await client.post(
        "/api/plugins/upload",
        files=_zip_files(),
        data={"force": "true"},
        headers=auth,
    )
    assert r3.status_code == 200, r3.text


async def test_upload_plugin_rejects_non_zip(env: Any) -> None:
    client, _srv, auth = env
    files = {"file": ("not-a-plugin.zip", b"<!DOCTYPE html>blob page", "application/zip")}
    r = await client.post("/api/plugins/upload", files=files, headers=auth)
    assert r.status_code == 400, r.text


async def test_upload_plugin_requires_admin(env_admin_alice: Any) -> None:
    client, _srv, _admin_auth, alice_auth = env_admin_alice
    r = await client.post("/api/plugins/upload", files=_zip_files(), headers=alice_auth)
    assert r.status_code == 403, r.text


async def test_list_plugins_is_available_to_authenticated_users(env_admin_alice: Any) -> None:
    client, _srv, _admin_auth, alice_auth = env_admin_alice
    response = await client.get("/api/plugins", headers=alice_auth)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("plugin_id", ["..", "../outside", "nested/plugin", "..\\outside"])
@pytest.mark.parametrize("force", [False, True])
async def test_upload_rejects_invalid_id_without_modifying_existing_files(
    env: Any, plugin_id: str, force: bool
) -> None:
    client, srv, auth = env
    plugins_dir = srv.plugin_manager.plugins_dir
    outside = plugins_dir.parent / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    existing = plugins_dir / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_text("existing", encoding="utf-8")

    response = await client.post(
        "/api/plugins/upload",
        files={"file": ("plugin.zip", _echo_zip(plugin_id), "application/zip")},
        data={"force": str(force).lower()},
        headers=auth,
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "PLUGIN_INVALID_ARCHIVE"
    assert response.json()["error"]["details"]["reason"] == "invalid_plugin_id"
    assert marker.read_text(encoding="utf-8") == "keep"
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "existing"
    assert list(plugins_dir.iterdir()) == [existing]
    assert list(outside.iterdir()) == [marker]


async def test_install_url_rejects_invalid_manifest_id(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, srv, auth = env

    def fake_retrieve(url: str, filename: str | Path) -> tuple[str, None]:
        Path(filename).write_bytes(_echo_zip("../outside"))
        return str(filename), None

    monkeypatch.setattr(
        "octop.infra.agents.plugins.manager.urllib.request.urlretrieve", fake_retrieve
    )
    response = await client.post(
        "/api/plugins/install", json={"url": "https://example.com/plugin.zip"}, headers=auth
    )

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "PLUGIN_INVALID_ARCHIVE"
    assert not (srv.plugin_manager.plugins_dir.parent / "outside").exists()


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
async def test_plugin_routes_reject_parent_directory_id(env: Any, method: str) -> None:
    client, srv, auth = env
    home = srv.plugin_manager.plugins_dir.parent
    manifest = home / "plugin.yaml"
    manifest.write_text("id: outside\nversion: 1.0.0\n", encoding="utf-8")
    marker = home / "private.txt"
    marker.write_text("private", encoding="utf-8")
    config = home / "config.json"
    config_before = config.read_bytes()
    path = "/api/plugins/%2e%2e"
    if method == "GET":
        path += "/ui/private.txt"
    kwargs = {"json": {"enabled": False}} if method == "PATCH" else {}

    response = await client.request(method, path, headers=auth, **kwargs)

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert marker.read_text(encoding="utf-8") == "private"
    assert config.read_bytes() == config_before
    assert srv.plugin_manager.plugins_dir.is_dir()
