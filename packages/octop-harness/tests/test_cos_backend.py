"""Unit tests for ``octop_harness.backends.cos.CosBackend``.

These run **offline** by injecting a fake ``CosS3Client``-like object that
behaves like an in-memory bucket. They exercise the protocol contract
(read/write/edit/ls/glob/grep, error handling, create-only semantics)
without hitting the network. A separate ``examples/05_cos_backend.py``
runs against a real bucket to validate the SDK integration.
"""

from __future__ import annotations

import io
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

import pytest

from octop_harness.backends.cos_backend import CosBackend, CosConfig


def _test_credential() -> str:
    """Return a non-production credential value for configuration tests."""
    return secrets.token_urlsafe(24)


# ---------------------------------------------------------------------------
# Fake CosS3Client
# ---------------------------------------------------------------------------


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def get_raw_stream(self) -> io.BytesIO:
        return self._buf


class _FakeCosServiceError(Exception):
    """Mirrors the relevant subset of qcloud_cos.cos_exception.CosServiceError."""

    def __init__(self, status_code: int, error_code: str = "NoSuchKey") -> None:
        super().__init__(f"{status_code} {error_code}")
        self._status = status_code
        self._error = error_code

    def get_status_code(self) -> int:
        return self._status

    def get_error_code(self) -> str:
        return self._error


# Patch the import path the backend uses for the exception type.
# autouse=False — applied explicitly by offline test classes only.
# Real-COS integration tests must NOT use this fixture, as it replaces
# the entire qcloud_cos.cos_exception module and breaks the real SDK import.
@pytest.fixture
def _patch_cos_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``qcloud_cos.cos_exception.CosServiceError`` resolve to our fake.

    The backend imports ``CosServiceError`` lazily inside ``_get_file_data``;
    we install our fake exception class globally for the duration of each test.
    """
    fake_module_name = "qcloud_cos.cos_exception"
    import sys
    import types

    fake_mod = types.ModuleType(fake_module_name)
    fake_mod.CosServiceError = _FakeCosServiceError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, fake_module_name, fake_mod)


class FakeCosClient:
    """An in-memory stand-in for ``CosS3Client``.

    Stores objects as ``{key: bytes}``; mimics ``put_object``,
    ``get_object`` and ``list_objects`` (with ``Delimiter='/'`` and
    pagination).
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.last_modified: dict[str, str] = {}

    # ----- COS API surface used by CosBackend -----

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs["Key"])
        body = kwargs["Body"]
        self.objects[key] = body if isinstance(body, bytes) else body.encode("utf-8")
        self.last_modified[key] = "2026-05-22T00:00:00.000Z"
        return {"ETag": '"fake-etag"'}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs["Key"])
        if key not in self.objects:
            raise _FakeCosServiceError(status_code=404, error_code="NoSuchKey")
        return {"Body": _FakeBody(self.objects[key])}

    def list_objects(self, **kwargs: Any) -> dict[str, Any]:
        prefix = str(kwargs.get("Prefix") or "")
        delimiter = str(kwargs.get("Delimiter") or "")
        marker = str(kwargs.get("Marker") or "")
        max_keys = int(kwargs.get("MaxKeys") or 1000)
        # Filter & sort.
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        contents: list[dict[str, Any]] = []
        common_prefixes: list[dict[str, Any]] = []
        seen_dirs: set[str] = set()

        for key in keys:
            if marker and key <= marker:
                continue
            if delimiter:
                rest = key[len(prefix) :]
                slash = rest.find(delimiter)
                if slash != -1:
                    dir_name = prefix + rest[: slash + 1]
                    if dir_name not in seen_dirs:
                        seen_dirs.add(dir_name)
                        common_prefixes.append({"Prefix": dir_name})
                    continue
            contents.append(
                {
                    "Key": key,
                    "Size": len(self.objects[key]),
                    "LastModified": self.last_modified.get(key, ""),
                },
            )
            if len(contents) >= max_keys:
                break

        return {
            "Contents": contents,
            "CommonPrefixes": common_prefixes,
            "IsTruncated": "false",
        }


@pytest.fixture
def fake_client() -> FakeCosClient:
    return FakeCosClient()


@pytest.fixture
def backend(fake_client: FakeCosClient, _patch_cos_exception: None) -> CosBackend:
    config = CosConfig(
        bucket="test-bucket-1234567890",
        region="ap-guangzhou",
        secret_id=_test_credential(),
        secret_key=_test_credential(),
        prefix="ws/",
    )
    return CosBackend(config, client=fake_client)


# ---------------------------------------------------------------------------
# CosConfig validation
# ---------------------------------------------------------------------------


class TestCosConfig:
    def test_required_fields(self) -> None:
        # All required fields → ok
        cfg = CosConfig(
            bucket="b-1",
            region="ap-guangzhou",
            secret_id=_test_credential(),
            secret_key=_test_credential(),
        )
        assert cfg.prefix == ""

    def test_missing_bucket(self) -> None:
        with pytest.raises(ValueError, match="bucket"):
            CosConfig(bucket="", region="r", secret_id=_test_credential(), secret_key=_test_credential())

    def test_missing_region(self) -> None:
        with pytest.raises(ValueError, match="region"):
            CosConfig(bucket="b", region="", secret_id=_test_credential(), secret_key=_test_credential())

    def test_missing_credentials(self) -> None:
        with pytest.raises(ValueError, match="secret_id"):
            CosConfig(bucket="b", region="r", secret_id="", secret_key=_test_credential())
        with pytest.raises(ValueError, match="secret_id"):
            CosConfig(bucket="b", region="r", secret_id=_test_credential(), secret_key="")

    def test_prefix_normalized(self) -> None:
        cfg = CosConfig(
            bucket="b",
            region="r",
            secret_id=_test_credential(),
            secret_key=_test_credential(),
            prefix="/work/",
        )
        # Slashes stripped from both ends.
        assert cfg.prefix == "work"


# ---------------------------------------------------------------------------
# Read / write / edit
# ---------------------------------------------------------------------------


class TestRead:
    def test_missing_file(self, backend: CosBackend) -> None:
        result = backend.read("/missing.txt")
        assert result.file_data is None
        assert "not found" in (result.error or "").lower()

    def test_round_trip(self, backend: CosBackend) -> None:
        backend.write("/notes.md", "# Hello\nLine 2")
        r = backend.read("/notes.md")
        assert r.error is None
        assert r.file_data is not None
        assert "Hello" in r.file_data["content"]


class TestWrite:
    def test_create_only(self, backend: CosBackend) -> None:
        first = backend.write("/a.txt", "v1")
        assert first.error is None
        assert first.path == "/a.txt"

        second = backend.write("/a.txt", "v2")
        assert second.error is not None
        assert "already exists" in second.error.lower()

    def test_stored_as_filedata_envelope(
        self,
        backend: CosBackend,
        fake_client: FakeCosClient,
    ) -> None:
        """The stored object is JSON containing ``content`` / ``encoding``."""
        backend.write("/x.txt", "hello")
        # The key includes the configured prefix.
        key = "ws/x.txt"
        assert key in fake_client.objects
        envelope = json.loads(fake_client.objects[key].decode("utf-8"))
        assert envelope["content"] == "hello"
        assert envelope["encoding"] == "utf-8"


class TestBinaryUpload:
    async def test_png_roundtrip_via_workspace(
        self, backend: CosBackend, fake_client: FakeCosClient, tmp_path: Path
    ) -> None:
        from octop_harness.backends.workspace import BackendWorkspace

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
        ws = BackendWorkspace(backend, tmp_path)
        await ws.aupload_bytes(".octop/avatar.png", png)
        stored_key = f"ws/.octop/workspaces/{tmp_path.name}/.octop/avatar.png"
        assert stored_key in fake_client.objects
        envelope = json.loads(fake_client.objects[stored_key].decode("utf-8"))
        assert envelope["encoding"] == "base64"
        got = await ws.adownload_bytes(".octop/avatar.png")
        assert got == png
        assert str(tmp_path) not in next(iter(fake_client.objects))

    async def test_workspace_files_land_under_virtual_folder(
        self, backend: CosBackend, fake_client: FakeCosClient, tmp_path: Path
    ) -> None:
        from octop_harness.backends.workspace import BackendWorkspace, remote_workspace_virtual_root

        virt = remote_workspace_virtual_root(tmp_path)
        ws = BackendWorkspace(backend, tmp_path)
        await ws.awrite_text("SOUL.md", "hello")
        await ws.awrite_text("skills/demo/SKILL.md", "skill")

        stored = f"ws{virt}/SOUL.md"
        assert stored in fake_client.objects
        assert "ws/SOUL.md" not in fake_client.objects
        assert str(tmp_path) not in stored

        root = backend.ls("/")
        root_paths = {e["path"] for e in root.entries or []}
        assert "/.octop" in root_paths
        assert all(e.get("is_dir") for e in root.entries or [] if e["path"] == "/.octop")

        workspaces = backend.ls("/.octop/workspaces")
        ws_paths = {e["path"] for e in workspaces.entries or []}
        assert virt in ws_paths

        listed = await ws.als(".")
        assert listed is not None
        presented = {row["path"].rstrip("/") for row in listed.entries or []}
        assert "SOUL.md" in presented
        assert "skills" in presented

    async def test_workspace_reads_legacy_flattened_root_file(
        self, backend: CosBackend, fake_client: FakeCosClient, tmp_path: Path
    ) -> None:
        from octop_harness.backends.workspace import BackendWorkspace

        backend.write("/SOUL.md", "legacy-root")
        ws = BackendWorkspace(backend, tmp_path)
        assert await ws.aread_text("SOUL.md") == "legacy-root"
        await ws.awrite_text("SOUL.md", "nested")
        assert await ws.aread_text("SOUL.md") == "nested"
        assert f"ws/.octop/workspaces/{tmp_path.name}/SOUL.md" in fake_client.objects


class TestEdit:
    def test_unique_replacement(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "alpha beta gamma")
        result = backend.edit("/a.txt", "beta", "BETA")
        assert result.error is None
        assert result.occurrences == 1

        r = backend.read("/a.txt")
        assert "alpha BETA gamma" in (r.file_data or {}).get("content", "")

    def test_ambiguous_without_replace_all(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "alpha beta alpha")
        result = backend.edit("/a.txt", "alpha", "AAA")
        assert result.error is not None  # framework signals ambiguity

    def test_replace_all(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "x y x y x")
        result = backend.edit("/a.txt", "x", "X", replace_all=True)
        assert result.error is None
        assert result.occurrences == 3

    def test_missing_file(self, backend: CosBackend) -> None:
        result = backend.edit("/never.txt", "a", "b")
        assert result.error is not None and "not found" in result.error.lower()


# ---------------------------------------------------------------------------
# Listing / globbing / grepping
# ---------------------------------------------------------------------------


class TestLs:
    def test_lists_top_level_files(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "x")
        backend.write("/b.txt", "y")
        backend.write("/sub/c.txt", "z")

        entries = backend.ls("/").entries or []
        paths = sorted(e["path"] for e in entries)
        # Expect both top-level files and a directory marker for /sub.
        assert "/a.txt" in paths
        assert "/b.txt" in paths
        # The directory entry for /sub should be present and marked is_dir.
        sub_dir = next((e for e in entries if e.get("is_dir")), None)
        assert sub_dir is not None
        assert sub_dir["path"].rstrip("/") == "/sub"

    def test_lists_subdirectory(self, backend: CosBackend) -> None:
        backend.write("/sub/c.txt", "z")
        entries = backend.ls("/sub/").entries or []
        assert [e["path"] for e in entries] == ["/sub/c.txt"]

    def test_metadata_present(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "abc")
        entries = backend.ls("/").entries or []
        a = next(e for e in entries if e["path"] == "/a.txt")
        assert a.get("is_dir") is False
        assert a.get("size", 0) > 0


class TestMkdir:
    def test_mkdir_path_creates_listable_directory(self, backend: CosBackend, fake_client: FakeCosClient) -> None:
        backend.mkdir_path("/.octop")
        assert "ws/.octop/" in fake_client.objects
        entries = backend.ls("/").entries or []
        octop_dir = next(e for e in entries if e.get("is_dir") and e["path"].rstrip("/") == "/.octop")
        assert octop_dir["is_dir"] is True
        assert sum(1 for e in entries if e["path"].rstrip("/") == "/.octop") == 1

    def test_mkdir_path_creates_parents(self, backend: CosBackend, fake_client: FakeCosClient) -> None:
        backend.mkdir_path("/a/b")
        assert "ws/a/" in fake_client.objects
        assert "ws/a/b/" in fake_client.objects

    def test_mkdir_path_rejects_existing_file(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "x")
        with pytest.raises(FileExistsError):
            backend.mkdir_path("/a.txt")


class TestGlobAndGrep:
    def test_glob_matches_pattern(self, backend: CosBackend) -> None:
        backend.write("/a.py", "x")
        backend.write("/b.py", "y")
        backend.write("/c.txt", "z")
        result = backend.glob("**/*.py", path="/")
        assert result.error is None
        matched_paths = sorted(m["path"] for m in (result.matches or []))
        assert matched_paths == ["/a.py", "/b.py"]

    def test_glob_no_match_returns_empty_list(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "x")
        result = backend.glob("**/*.does-not-exist", path="/")
        assert result.error is None
        assert result.matches == []

    def test_grep_finds_pattern(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "first line\nthe magic word is FOO\nthird line")
        backend.write("/b.txt", "no match here")
        result = backend.grep("magic word", path="/")
        assert result.error is None
        matches = result.matches or []
        assert len(matches) == 1
        assert matches[0]["path"] == "/a.txt"
        assert "magic word" in matches[0]["text"]

    def test_grep_no_matches(self, backend: CosBackend) -> None:
        backend.write("/a.txt", "nothing interesting here")
        result = backend.grep("ZZZZZZ", path="/")
        assert result.error is None
        assert result.matches == []


# ---------------------------------------------------------------------------
# resolve_backend integration
# ---------------------------------------------------------------------------


class TestResolveBackendIntegration:
    def test_resolve_cos_string_with_kwargs(self, monkeypatch: pytest.MonkeyPatch, _patch_cos_exception: None) -> None:
        from octop_harness.backends import resolve_backend

        # Provide a fake CosS3Client so we don't try to talk to real network.
        fake = FakeCosClient()
        from octop_harness.backends import cos_backend as cos_module

        monkeypatch.setattr(cos_module.CosBackend, "_build_client", staticmethod(lambda _config: fake))

        backend = resolve_backend(
            {
                "type": "cos",
                "bucket": "b-1",
                "region": "ap-guangzhou",
                "secret_id": "x",
                "secret_key": "y",
                "prefix": "ws/",
            },
        )
        assert isinstance(backend, CosBackend)
        # Sanity check: a write/read cycle goes through the fake client.
        backend.write("/hello.txt", "hi")
        assert "ws/hello.txt" in fake.objects


# ---------------------------------------------------------------------------
# Real-COS integration tests (skipped unless COS_* env vars are present)
# ---------------------------------------------------------------------------

_COS_ENV_VARS = ("COS_BUCKET", "COS_REGION", "COS_SECRET_ID", "COS_SECRET_KEY")
_has_cos_creds = all(os.environ.get(v) for v in _COS_ENV_VARS)
_cos_skip = pytest.mark.skipif(
    not _has_cos_creds,
    reason="COS_BUCKET / COS_REGION / COS_SECRET_ID / COS_SECRET_KEY not set",
)
_RUN_ID = os.environ.get("COS_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")


def _real_cos_backend(prefix_suffix: str) -> CosBackend:
    """Build a real CosBackend scoped to a per-run prefix."""
    config = CosConfig(
        bucket=os.environ["COS_BUCKET"],
        region=os.environ["COS_REGION"],
        secret_id=os.environ["COS_SECRET_ID"],
        secret_key=os.environ["COS_SECRET_KEY"],
        prefix=f"pytest/{_RUN_ID}/{prefix_suffix}/",
    )
    return CosBackend(config)


@_cos_skip
class TestRealCosBackend:
    """Integration tests that hit the real Tencent COS bucket.

    Each test method uses a unique prefix inside ``pytest/<RUN_ID>/``
    to avoid cross-test collisions given CosBackend's write-once semantics.
    """

    def test_write_and_read(self) -> None:
        backend = _real_cos_backend("write-read")
        w = backend.write("/hello.txt", "Hello COS - ni hao!")
        assert w.error is None, f"write error: {w.error}"

        r = backend.read("/hello.txt")
        assert r.error is None, f"read error: {r.error}"
        content = (r.file_data or {}).get("content", "")
        assert content == "Hello COS - ni hao!", f"unexpected content: {content!r}"

    def test_write_twice_returns_error(self) -> None:
        backend = _real_cos_backend("write-twice")
        backend.write("/dup.txt", "first")
        r2 = backend.write("/dup.txt", "second")
        assert r2.error is not None, "Expected error on duplicate write"

    def test_edit(self) -> None:
        backend = _real_cos_backend("edit")
        backend.write("/greet.txt", "Hello World")
        e = backend.edit("/greet.txt", "Hello", "Hi")
        assert e.error is None, f"edit error: {e.error}"
        assert e.occurrences == 1

        r = backend.read("/greet.txt")
        assert (r.file_data or {}).get("content") == "Hi World"

    def test_ls(self) -> None:
        backend = _real_cos_backend("ls")
        backend.write("/a.txt", "a")
        backend.write("/b.txt", "b")

        result = backend.ls("/")
        assert result.error is None
        paths = [(e.get("path") if isinstance(e, dict) else getattr(e, "path", "")) for e in (result.entries or [])]
        assert any("/a.txt" in p for p in paths), f"a.txt missing from ls: {paths}"
        assert any("/b.txt" in p for p in paths), f"b.txt missing from ls: {paths}"

    def test_glob(self) -> None:
        backend = _real_cos_backend("glob")
        backend.write("/doc.md", "# doc")
        backend.write("/readme.txt", "readme")

        result = backend.glob("/*.md", path="/")
        assert result.error is None
        matches = result.matches or []
        match_paths = [m["path"] if isinstance(m, dict) else getattr(m, "path", "") for m in matches]
        assert any("doc.md" in p for p in match_paths), f"doc.md not in glob: {match_paths}"
        assert not any("readme.txt" in p for p in match_paths), "readme.txt leaked into *.md glob"

    def test_grep(self) -> None:
        backend = _real_cos_backend("grep")
        backend.write("/a.txt", "the magic word is ORCA\nsecond line")
        backend.write("/b.txt", "nothing here")

        result = backend.grep("ORCA", path="/")
        assert result.error is None
        matches = result.matches or []
        assert len(matches) == 1
        assert "ORCA" in matches[0]["text"]


@_cos_skip
class TestRealCosCompositeMount:
    """Integration tests for composite backend with real COS + local_shell.

    Verifies the real-filesystem-mount scenario: default route writes to
    disk, /cos/ route writes to the real COS bucket.
    """

    def _composite_spec(self, local_root: Path, prefix_suffix: str) -> dict[str, object]:
        return {
            "type": "composite",
            "default": {
                "type": "local_shell",
                "root_dir": str(local_root),
                # virtual_mode=True: /disk-note.txt → {local_root}/disk-note.txt
                # This is the standard "workspace + /cos/ overlay" pattern.
                "virtual_mode": True,
            },
            "routes": {
                "/cos/": {
                    "type": "cos",
                    "bucket": os.environ["COS_BUCKET"],
                    "region": os.environ["COS_REGION"],
                    "secret_id": os.environ["COS_SECRET_ID"],
                    "secret_key": os.environ["COS_SECRET_KEY"],
                    "prefix": f"pytest/{_RUN_ID}/{prefix_suffix}/",
                },
            },
        }

    def test_local_write_lands_on_disk(self, tmp_path: Path) -> None:
        from octop_harness.backends import resolve_backend

        backend = resolve_backend(self._composite_spec(tmp_path, "composite-disk"), workspace_dir=tmp_path)

        r = backend.write("/disk-note.txt", "on disk")
        assert r.error is None, f"write error: {r.error}"

        # File must exist on real disk under tmp_path.
        disk_path = tmp_path / "disk-note.txt"
        assert disk_path.is_file(), f"File not found on disk: {disk_path}"
        assert disk_path.read_text(encoding="utf-8") == "on disk"

    def test_cos_write_does_not_land_on_disk(self, tmp_path: Path) -> None:
        from octop_harness.backends import resolve_backend

        backend = resolve_backend(self._composite_spec(tmp_path, "composite-cos"), workspace_dir=tmp_path)

        r = backend.write("/cos/cloud-note.txt", "in COS")
        assert r.error is None, f"COS write error: {r.error}"

        # Must NOT be on local disk.
        leaked = tmp_path / "cos" / "cloud-note.txt"
        assert not leaked.exists(), f"COS write leaked to disk at {leaked}"

        # Must be readable via the composite handle.
        read = backend.read("/cos/cloud-note.txt")
        assert read.error is None, f"COS read error: {read.error}"
        assert (read.file_data or {}).get("content") == "in COS"

    def test_ls_distinguishes_routes(self, tmp_path: Path) -> None:
        from octop_harness.backends import resolve_backend

        backend = resolve_backend(self._composite_spec(tmp_path, "composite-ls"), workspace_dir=tmp_path)

        backend.write("/local-file.txt", "local")
        backend.write("/cos/cos-file.txt", "cos")

        # ls /cos/ should only show the COS file.
        ls_cos = backend.ls("/cos/")
        cos_paths = [(e.get("path") if isinstance(e, dict) else getattr(e, "path", "")) for e in (ls_cos.entries or [])]
        assert any("cos-file.txt" in p for p in cos_paths), f"cos-file not in /cos/ ls: {cos_paths}"
        assert not any("local-file.txt" in p for p in cos_paths), "local-file leaked into /cos/ ls"

        # ls / on the composite backend with non-virtual local_shell returns
        # real filesystem entries under tmp_path — confirm local-file.txt is there.
        read_back = backend.read("/local-file.txt")
        assert read_back.error is None, f"local read error: {read_back.error}"
        assert (read_back.file_data or {}).get("content") == "local"

    def test_unknown_kwarg_raises_clear_error(self) -> None:
        from octop_harness.backends import resolve_backend

        with pytest.raises(TypeError):
            resolve_backend(
                {
                    "type": "cos",
                    "bucket": "b",
                    "region": "r",
                    "secret_id": "x",
                    "secret_key": "y",
                    "totally-bogus-kwarg": 42,
                },
            )
