"""T-68 verification additions for the portable surface (gaps `sec` disclosed).

The T-56/T-57 deliverables leave two things unpinned; this file pins them from the
outside, without touching production source.

⑤ **``dry_run=True`` must still run the AUD-2 scope gate.** In
   :func:`memory_portable.adopt_agent_memory` the validations run *before*
   ``adopt()`` and outside any ``dry_run`` branch — but nothing stops a later
   refactor from moving them inside ``if not dry_run``. A dry run must not become
   a way to probe the scope gate. Both sides are asserted (refuse **and** allow),
   because a gate with only its refusal side has no discriminating power.

⑥ **``doctor`` accepts the same ``host:namespace`` form as ``adopt`` but does not
   pass it through** :func:`resolve_namespace_to_adopt`. The last test here pins the
   *current* behaviour so the asymmetry is explicit and any future change is
   deliberate. It is a read-only diagnostic whose ``db_path`` the server resolves
   itself, so the asymmetry is labelling-only — recorded as a finding in
   ``VERIFY-T22.md``, not as an endorsement.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers import memory_portable as mp
from octop.infra.agents.memory.portable import namespace_scope as ns
from octop.infra.errors import ErrorCode, OctopError

AGENT_ID = "a1"


class _PkgFile:
    def __init__(self, payload: bytes = b"not-a-real-package") -> None:
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


def _user(*, uid: int = 1, is_admin: bool = False) -> Any:
    return SimpleNamespace(id=uid, is_admin=is_admin)


def _server(*, owner_id: int = 1, workspace: Path | None = None) -> Any:
    base = workspace if workspace is not None else Path("/tmp/octop-t68-ws") / AGENT_ID
    row = SimpleNamespace(agent_id=AGENT_ID, user_id=owner_id, is_shared=0, config_json="{}")
    registry = SimpleNamespace(
        get_row=lambda agent_id: row if agent_id == AGENT_ID else None,
        resolve_workspace_dir=lambda agent_id: base,
    )
    return SimpleNamespace(
        app_runtime=SimpleNamespace(agent_registry=registry),
        services=SimpleNamespace(agent_repo=SimpleNamespace(get=lambda agent_id: row)),
        paths=SimpleNamespace(ensure_agent_workspace=lambda agent_id: base),
    )


class _AdoptSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, pkg_path: Any, target_host: str, **kwargs: Any) -> Any:
        self.calls.append({"target_host": target_host, **kwargs})
        return SimpleNamespace(to_dict=lambda: {"target_namespace": kwargs.get("target_namespace")})


@pytest.fixture
def adopt_env(monkeypatch: pytest.MonkeyPatch) -> _AdoptSpy:
    """Same two stand-ins the T-56/T-57 files use: PG refusal + in-package manifest."""
    import octop_memory.operations.migration.portable as portable_pkg

    spy = _AdoptSpy()
    monkeypatch.setattr(portable_pkg, "adopt", spy)
    monkeypatch.setattr(mp, "_refuse_postgres_portable", lambda *_a, **_k: None)
    monkeypatch.setattr(mp, "_read_manifest_or_value_error", lambda _path: {"agent_name": AGENT_ID})
    return spy


async def _call(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "agent_id": AGENT_ID,
        "pkg_file": _PkgFile(),
        "target_host": "agent",
        "target_namespace": None,
        "on_conflict": "skip",
        "host_rewrite": "keep",
        "dry_run": True,
        "user": _user(),
        "server": _server(),
        "as_user": None,
    }
    kwargs.update(overrides)
    return await mp.adopt_agent_memory(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ dry_run must not skip the scope gate
# ─────────────────────────────────────────────────────────────────────────────


async def test_dry_run_still_refuses_a_foreign_project_namespace(
    adopt_env: _AdoptSpy,
) -> None:
    """Refusal side: a dry run must not become a probe for someone else's ns."""
    with pytest.raises(OctopError) as excinfo:
        await _call(target_namespace="project_P1", dry_run=True)

    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert excinfo.value.status == 403
    assert adopt_env.calls == [], "拒绝必须发生在 adopt() 之前，dry_run 也不例外"


async def test_dry_run_still_refuses_a_traversal_namespace(
    adopt_env: _AdoptSpy,
) -> None:
    """The format gate is also outside the ``dry_run`` branch."""
    with pytest.raises(OctopError) as excinfo:
        await _call(target_namespace="../evil", dry_run=True)

    assert excinfo.value.code == ErrorCode.SLASH_BAD_ARGS
    assert adopt_env.calls == []


async def test_dry_run_still_refuses_a_malformed_in_package_manifest(
    monkeypatch: pytest.MonkeyPatch, adopt_env: _AdoptSpy
) -> None:
    """``assert_manifest_scope_is_safe`` likewise precedes ``adopt()`` on a dry run.

    Note the code is ``SLASH_BAD_ARGS`` (400), not 403: the manifest channel is
    gated for **well-formedness** only — the cross-namespace refusal belongs to the
    form channels via ``resolve_namespace_to_adopt``. Getting this wrong in either
    direction is how a "safety" test ends up asserting nothing.
    """
    monkeypatch.setattr(
        mp,
        "_read_manifest_or_value_error",
        lambda _path: {"agent_name": "../../pwned"},
    )
    with pytest.raises(OctopError) as excinfo:
        await _call(target_namespace=ns.allowed_agent_namespace(AGENT_ID), dry_run=True)

    assert excinfo.value.code == ErrorCode.SLASH_BAD_ARGS
    assert adopt_env.calls == []


async def test_dry_run_passes_the_flag_through_when_the_scope_is_the_agents_own(
    adopt_env: _AdoptSpy,
) -> None:
    """Allow side — without this the three refusals above could pass vacuously.

    Also pins that ``dry_run`` really reaches the third-party adopter (a route that
    silently swallowed the flag would make "dry run" a real write).
    """
    await _call(target_namespace=ns.allowed_agent_namespace(AGENT_ID), dry_run=True)

    assert len(adopt_env.calls) == 1
    assert adopt_env.calls[0]["dry_run"] is True
    assert adopt_env.calls[0]["target_namespace"] == ns.allowed_agent_namespace(AGENT_ID)


async def test_the_same_boundary_holds_when_not_dry_running(
    adopt_env: _AdoptSpy,
) -> None:
    """Differential control: the refusal is identical with ``dry_run=False``.

    If this ever diverges from the dry-run case, the gate has been moved into the
    ``not dry_run`` branch.
    """
    with pytest.raises(OctopError) as excinfo:
        await _call(target_namespace="project_P1", dry_run=False)

    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert adopt_env.calls == []


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ doctor: ownership is enforced; host_spec is NOT scope-gated (pinned)
# ─────────────────────────────────────────────────────────────────────────────


class _DoctorSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, host_spec: str, **kwargs: Any) -> Any:
        self.calls.append({"host_spec": host_spec, **kwargs})
        return SimpleNamespace(to_dict=lambda: {"host_spec": host_spec, "ok": True})


@pytest.fixture
def doctor_env(monkeypatch: pytest.MonkeyPatch) -> _DoctorSpy:
    import octop_memory.operations.migration.portable as portable_pkg

    spy = _DoctorSpy()
    monkeypatch.setattr(portable_pkg, "doctor", spy)
    monkeypatch.setattr(mp, "_refuse_postgres_portable", lambda *_a, **_k: None)
    return spy


async def test_doctor_refuses_a_caller_who_does_not_own_the_agent(
    doctor_env: _DoctorSpy, tmp_path: Path
) -> None:
    """Ownership still applies to the read-only diagnostic."""
    with pytest.raises(OctopError):
        await mp.doctor_agent_memory(
            agent_id=AGENT_ID,
            host_spec="agent",
            compare_pkg=None,
            user=_user(uid=1),
            server=_server(owner_id=2, workspace=tmp_path),
            as_user=None,
        )
    assert doctor_env.calls == [], "越权必须在 doctor() 之前被拒"


async def test_doctor_host_spec_namespace_is_accepted_today_and_db_path_is_server_side(
    doctor_env: _DoctorSpy, tmp_path: Path
) -> None:
    """**Pins the asymmetry** (finding, not endorsement).

    ``doctor`` takes the same ``host:namespace`` spelling as ``adopt`` but never
    calls :func:`resolve_namespace_to_adopt`, so a foreign namespace in
    ``host_spec`` is passed straight to the third-party ``doctor()``. The blast
    radius is bounded by the next assertion: the ``db_path`` handed over is the
    one the **server** resolved for this agent, so the namespace cannot redirect
    which file is read.

    If the team decides ``doctor`` should be scope-gated too, this test flips to
    ``pytest.raises`` — that is the point of pinning it.

    ⚠️ **IF ``doctor`` EVER BECOMES A WRITE OPERATION, FLIP THIS TEST TO
    ``pytest.raises``.** The asymmetry is benign *only* because nothing here
    writes; the moment that stops being true, this test is the thing that must
    fail. Lead ruling (T-22): register the asymmetry, do not gate it — so this
    tripwire is the whole mitigation. Keep it, and keep this comment.
    """
    response = await mp.doctor_agent_memory(
        agent_id=AGENT_ID,
        host_spec="agent:project_P1",
        compare_pkg=None,
        user=_user(uid=1),
        server=_server(owner_id=1, workspace=tmp_path),
        as_user=None,
    )

    assert response.status_code == 200
    assert len(doctor_env.calls) == 1
    assert doctor_env.calls[0]["host_spec"] == "agent:project_P1"

    # The file that gets read is the server's own resolution for this agent,
    # not anything derived from the namespace embedded in host_spec.
    from octop.api.common.memory_client import memory_db_path_for_cfg

    assert doctor_env.calls[0]["db_path"] == str(memory_db_path_for_cfg(tmp_path, {}))
    assert not Path(doctor_env.calls[0]["db_path"]).is_absolute() or str(
        doctor_env.calls[0]["db_path"]
    ).startswith(str(tmp_path))


async def test_doctor_reports_a_bad_package_as_an_error_and_leaves_no_temp_file(
    doctor_env: _DoctorSpy, tmp_path: Path
) -> None:
    """A failing ``doctor()`` becomes one 500 envelope and does not leak the temp copy."""
    import tempfile

    import octop_memory.operations.migration.portable as portable_pkg

    before = set(Path(tempfile.gettempdir()).glob("tmp*.hmpkg"))
    original = portable_pkg.doctor

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("doctor exploded")

    portable_pkg.doctor = _boom  # type: ignore[assignment]
    try:
        with pytest.raises(OctopError) as excinfo:
            await mp.doctor_agent_memory(
                agent_id=AGENT_ID,
                host_spec="agent",
                compare_pkg=_PkgFile(b"not-a-zip"),
                user=_user(uid=1),
                server=_server(owner_id=1, workspace=tmp_path),
                as_user=None,
            )
        assert excinfo.value.code == ErrorCode.INTERNAL_ERROR
    finally:
        portable_pkg.doctor = original  # type: ignore[assignment]

    after = set(Path(tempfile.gettempdir()).glob("tmp*.hmpkg"))
    assert after - before == set(), "the uploaded temp copy must be unlinked on failure"
