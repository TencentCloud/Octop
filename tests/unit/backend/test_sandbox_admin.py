"""tests/unit/backend/test_sandbox_admin.py — ledger / drift / recreate / backups."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from octop.infra.backend.sandbox_admin import (
    LABEL_AGENT_ID,
    LABEL_SANDBOX,
    LABEL_SCOPE,
    SandboxAdminService,
    _network_offline,
)
from octop.infra.errors import ErrorCode, OctopError

# -- fake docker client -------------------------------------------------------


@dataclass
class FakeNetworks:
    networks: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeContainer:
    name: str
    image: str
    labels: dict[str, str]
    status: str = "running"
    created: str = "2026-10-23T00:00:00"
    networks: dict[str, Any] = field(default_factory=lambda: {"none": {}})
    working_dir: str = "/workspace/agent-1"
    removed: bool = False
    archive_files: dict[str, bytes] = field(default_factory=dict)
    id: str = "containerid123456"

    @property
    def attrs(self) -> dict[str, Any]:
        return {
            "Config": {
                "Image": self.image,
                "Labels": self.labels,
                "WorkingDir": self.working_dir,
            },
            "State": {"Status": self.status},
            "Created": self.created,
            "NetworkSettings": {"Networks": self.networks},
        }

    def get_archive(self, path: str) -> tuple[Any, Any]:
        import io
        import tarfile

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for fname, content in self.archive_files.items():
                info = tarfile.TarInfo(name=f"{Path(path).name}/{fname}")
                info.size = len(content)
                tf.addfile(info, io.BytesIO(content))
        buf.seek(0)
        return buf, {"name": Path(path).name, "size": buf.getbuffer().nbytes}

    def remove(self, force: bool = False) -> None:  # noqa: ARG002
        self.removed = True


@dataclass
class FakeContainers:
    items: list[FakeContainer]

    def list(
        self, *, all: bool = False, filters: dict[str, Any] | None = None
    ) -> list[FakeContainer]:  # noqa: A002, ARG002
        label = (filters or {}).get("label", "")
        key, _, want = label.partition("=")
        return [c for c in self.items if c.labels.get(key) == want]

    def get(self, name: str) -> FakeContainer:
        for c in self.items:
            if c.name == name:
                return c
        raise KeyError(name)


@dataclass
class FakeImages:
    tags: list[str] = field(default_factory=list)

    def list(self) -> list[dict[str, Any]]:
        return [
            {"attrs": {"RepoTags": [t], "Size": 1000, "Created": "1"}, "id": f"img{i}"}
            for i, t in enumerate(self.tags)
        ]


@dataclass
class FakeClient:
    containers: FakeContainers
    images: FakeImages = field(default_factory=FakeImages)

    def ping(self) -> None:
        return None


# -- fakes for services / runtime --------------------------------------------


@dataclass
class FakeRow:
    name: str
    kind: str = "docker"
    config_json: str | None = None


class FakeBackendRepo:
    def __init__(self, rows: list[FakeRow]) -> None:
        self.rows = rows

    def list_all(self) -> list[FakeRow]:
        return self.rows

    def get_by_name(self, name: str) -> FakeRow | None:
        for row in self.rows:
            if row.name == name:
                return row
        return None


@dataclass
class FakeAgentRow:
    agent_id: str
    name: str


class FakeRegistry:
    def __init__(
        self,
        rows: dict[str, FakeAgentRow],
        configs: dict[str, dict[str, Any]],
        active: set[str] | None = None,
        backend_repo: Any | None = None,
    ) -> None:
        self._rows = rows
        self._configs = configs
        self._active = active or set()
        self._backend_repo = backend_repo

    def get_row(self, agent_id: str) -> FakeAgentRow | None:
        return self._rows.get(agent_id)

    def list_rows(self) -> list[FakeAgentRow]:
        return list(self._rows.values())

    def get_config(self, agent_id: str) -> dict[str, Any]:
        return self._configs.get(agent_id, {})

    def find_agents_using_storage_backend(self, name: str) -> list[dict[str, Any]]:
        return [
            {"agent_id": aid}
            for aid, cfg in self._configs.items()
            if isinstance(cfg.get("backend"), dict)
            and cfg["backend"].get("type") == "named"
            and cfg["backend"].get("name") == name
        ]

    def is_agent_active(self, agent_id: str) -> bool:
        return agent_id in self._active

    def _backend_spec_for_row(self, row: FakeAgentRow) -> Any:
        from octop.infra.backend.resolver import resolve_agent_backend_spec

        return resolve_agent_backend_spec(
            self._configs.get(row.agent_id, {}).get("backend"),
            repo=self._backend_repo,
        )


@dataclass
class FakeServices:
    storage_backend_repo: FakeBackendRepo


@dataclass
class FakeRuntime:
    agent_registry: FakeRegistry


def make_service(
    containers: list[FakeContainer],
    *,
    backend_rows: list[FakeRow] | None = None,
    rows: dict[str, FakeAgentRow] | None = None,
    configs: dict[str, dict[str, Any]] | None = None,
    active: set[str] | None = None,
    backup_root: Path | None = None,
    client: FakeClient | None = None,
) -> SandboxAdminService:
    repo = FakeBackendRepo(backend_rows or [])
    if client is None:
        client = FakeClient(containers=FakeContainers(containers))
    return SandboxAdminService(
        services=FakeServices(repo),
        app_runtime=FakeRuntime(FakeRegistry(rows or {}, configs or {}, active, backend_repo=repo)),
        client=client,
        backup_root=backup_root,
    )


def sandbox_container(name: str, **kw: Any) -> FakeContainer:
    labels = {
        LABEL_SANDBOX: "1",
        LABEL_SCOPE: kw.pop("scope", "agent"),
        LABEL_AGENT_ID: kw.pop("agent_id", "a1"),
    }
    kw.setdefault("labels", labels)
    return FakeContainer(name=name, **kw)


# -- unit tests ---------------------------------------------------------------


def test_network_offline_detection() -> None:
    assert _network_offline(FakeContainer("c", "img", {}, networks={"none": {}})) is True
    assert _network_offline(FakeContainer("c", "img", {}, networks={"bridge": {}})) is False
    assert _network_offline(FakeContainer("c", "img", {}, networks={})) is True


def test_ledger_agent_scope_no_drift(tmp_path: Path) -> None:
    configs = {"a1": {"backend": {"type": "docker", "image": "sb:1.0.0"}}}
    svc = make_service(
        [
            sandbox_container(
                "agentbuddy_sandbox_a1",
                image="sb:1.0.0",
            )
        ],
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        backup_root=tmp_path,
    )
    entries = svc.list_sandboxes()
    assert len(entries) == 1
    e = entries[0]
    assert e.expected_image == "sb:1.0.0"
    assert e.expected_allow_network is False
    assert e.drift is False
    assert e.network_drift is False
    assert e.network_offline is True
    assert e.affected_agents == [{"agent_id": "a1", "name": "Alpha"}]


def test_ledger_network_drift_online_but_should_be_offline(tmp_path: Path) -> None:
    configs = {"a1": {"backend": {"type": "docker", "image": "sb:1.0.0"}}}
    svc = make_service(
        [
            sandbox_container(
                "agentbuddy_sandbox_a1",
                image="sb:1.0.0",
                networks={"bridge": {}},
            )
        ],
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        backup_root=tmp_path,
    )
    (e,) = svc.list_sandboxes()
    assert e.network_drift is True  # expected offline, container online
    assert e.drift is False


def test_ledger_image_drift(tmp_path: Path) -> None:
    configs = {"a1": {"backend": {"type": "docker", "image": "sb:2.0.0"}}}
    svc = make_service(
        [sandbox_container("agentbuddy_sandbox_a1", image="sb:1.0.0")],
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        backup_root=tmp_path,
    )
    (e,) = svc.list_sandboxes()
    assert e.drift is True
    assert e.expected_image == "sb:2.0.0"


def test_ledger_named_backend_expected_values(tmp_path: Path) -> None:
    backend_rows = [
        FakeRow(
            name="docker-online",
            config_json=json.dumps({"image": "sb:3.0.0", "allow_network": True}),
        )
    ]
    configs = {"a1": {"backend": {"type": "named", "name": "docker-online"}}}
    svc = make_service(
        [
            sandbox_container(
                "agentbuddy_sandbox_a1",
                image="sb:2.0.0",
                networks={"bridge": {}},
            )
        ],
        backend_rows=backend_rows,
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        backup_root=tmp_path,
    )
    (e,) = svc.list_sandboxes()
    assert e.expected_image == "sb:3.0.0"
    assert e.expected_allow_network is True
    assert e.network_offline is False
    assert e.network_drift is False  # expected online, container online
    assert e.drift is True


def test_ledger_unknown_expected_no_drift_claim(tmp_path: Path) -> None:
    svc = make_service(
        [sandbox_container("agentbuddy_sandbox_ghost", image="sb:x")],
        backup_root=tmp_path,
    )
    (e,) = svc.list_sandboxes()
    assert e.expected_image is None
    assert e.drift is None
    assert e.network_drift is None


def test_recreate_success_backs_up_and_removes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import octop_harness.backends.docker_sandbox as ds

    monkeypatch.setattr(ds, "ensure_docker_image", lambda *_a, **_kw: None)
    container = sandbox_container(
        "agentbuddy_sandbox_a1",
        image="sb:1.0.0",
        archive_files={"SOUL.md": b"hello"},
    )
    configs = {"a1": {"backend": {"type": "docker", "image": "sb:2.0.0"}}}
    svc = make_service(
        [container],
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        backup_root=tmp_path,
    )
    result = svc.recreate("agentbuddy_sandbox_a1")
    assert result["recreated"] is True
    assert result["old_image"] == "sb:1.0.0"
    assert result["expected_image"] == "sb:2.0.0"
    assert result["expected_allow_network"] is False
    assert container.removed is True
    backup = Path(result["backup_path"])
    assert (backup / "meta.json").is_file()
    extracted = list((backup / "workspace").rglob("SOUL.md"))
    assert len(extracted) == 1
    assert extracted[0].read_bytes() == b"hello"


def test_recreate_refuses_active_conversation(tmp_path: Path) -> None:
    configs = {"a1": {"backend": {"type": "docker", "image": "sb:1.0.0"}}}
    svc = make_service(
        [sandbox_container("agentbuddy_sandbox_a1", image="sb:1.0.0")],
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        active={"a1"},
        backup_root=tmp_path,
    )
    with pytest.raises(OctopError) as exc_info:
        svc.recreate("agentbuddy_sandbox_a1")
    assert exc_info.value.code == ErrorCode.SANDBOX_IN_USE


def test_recreate_refuses_non_sandbox_container(tmp_path: Path) -> None:
    svc = make_service(
        [
            FakeContainer(
                "nginx",
                "nginx:latest",
                labels={},
            )
        ],
        backup_root=tmp_path,
    )
    with pytest.raises(OctopError) as exc_info:
        svc.recreate("nginx")
    assert exc_info.value.code == ErrorCode.SANDBOX_LABEL_MISMATCH


def test_recreate_missing_image_keeps_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_a: Any, **_kw: Any) -> None:
        raise RuntimeError("pull failed")

    import octop_harness.backends.docker_sandbox as ds

    monkeypatch.setattr(ds, "ensure_docker_image", _boom)
    container = sandbox_container("agentbuddy_sandbox_a1", image="sb:1.0.0")
    configs = {"a1": {"backend": {"type": "docker", "image": "sb:2.0.0"}}}
    svc = make_service(
        [container],
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        backup_root=tmp_path,
    )
    with pytest.raises(OctopError) as exc_info:
        svc.recreate("agentbuddy_sandbox_a1")
    assert exc_info.value.code == ErrorCode.SANDBOX_IMAGE_MISSING
    assert container.removed is False  # old container kept


def test_image_inventory_flags_referenced(tmp_path: Path) -> None:
    configs = {"a1": {"backend": {"type": "docker", "image": "sb:1.0.0"}}}
    client = FakeClient(
        containers=FakeContainers([sandbox_container("agentbuddy_sandbox_a1", image="sb:1.0.0")]),
        images=FakeImages(tags=["sb:1.0.0", "sb:2.0.0", "python:3.12"]),
    )
    svc = make_service(
        [sandbox_container("agentbuddy_sandbox_a1", image="sb:1.0.0")],
        rows={"a1": FakeAgentRow("a1", "A")},
        configs=configs,
        backup_root=tmp_path,
        client=client,
    )
    rows = svc.list_images()
    ref = {r["tag"]: r["referenced"] for r in rows}
    assert ref["sb:1.0.0"] is True
    assert ref["sb:2.0.0"] is False
    assert ref["python:3.12"] is False


def test_ledger_user_scope_lists_affected_experts(tmp_path: Path) -> None:
    """user-scope container: affected experts found via inline docker prefix
    even when no named reference exists (the empty-panel bug)."""
    configs = {
        "a1": {
            "backend": {
                "type": "docker",
                "image": "sb:1.0.0",
                "sandbox_scope": "user",
                "sandbox_prefix": "agentbuddy_sandbox",
            }
        },
    }
    svc = make_service(
        [
            sandbox_container(
                "agentbuddy_sandbox_hk",
                image="sb:1.0.0",
                scope="user",
                agent_id="a1",
            )
        ],
        rows={"a1": FakeAgentRow("a1", "Net Expert")},
        configs=configs,
        backup_root=tmp_path,
    )
    (e,) = svc.list_sandboxes()
    assert e.scope == "user"
    assert e.affected_agents == [{"agent_id": "a1", "name": "Net Expert"}]
    # expected values resolved from the inline backend
    assert e.expected_image == "sb:1.0.0"
    assert e.expected_allow_network is False


def test_user_scope_prefix_with_underscored_username(tmp_path: Path) -> None:
    """Prefix derivation prefers a known sandbox_prefix over rsplit, so
    usernames containing underscores do not corrupt the prefix."""
    configs = {
        "a1": {
            "backend": {
                "type": "docker",
                "image": "sb:1.0.0",
                "sandbox_prefix": "agentbuddy_sandbox",
            }
        },
    }
    svc = make_service(
        [
            sandbox_container(
                "agentbuddy_sandbox_hk_user",
                image="sb:1.0.0",
                scope="user",
                agent_id="a1",
            )
        ],
        rows={"a1": FakeAgentRow("a1", "Alpha")},
        configs=configs,
        backup_root=tmp_path,
    )
    (e,) = svc.list_sandboxes()
    assert e.affected_agents == [{"agent_id": "a1", "name": "Alpha"}]
    assert e.expected_image == "sb:1.0.0"
