"""S3 storage backends must satisfy the installed deepagents protocol (issue #780).

``harness_agent.backends._build_s3`` prefers ``deepagents_backends.S3Backend``
whenever that package is importable, and only falls back to its own boto3
backend on ``ImportError``.  ``deepagents-backends 0.2.0`` still targets the
deepagents 0.5/0.6 protocol, so with deepagents 0.7 installed:

* ``write`` / ``edit`` raise ``TypeError: ... unexpected keyword argument
  'files_update'`` on their success path, and
* ``ls`` / ``glob`` / ``grep`` are not implemented at all (only the removed
  ``ls_info`` / ``glob_info`` / ``grep_raw`` names are), so ``ls`` inherits the
  ``NotImplementedError`` stub from ``BackendProtocol``.

Octop therefore must not pull ``deepagents-backends`` in, which means declaring
narrower ``orcakit-harness-agent`` extras instead of ``[all]``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_PYPROJECT = _REPO / "pyproject.toml"

# Extras Octop genuinely relies on. ``remote-backends`` is intentionally absent:
# it is the only extra that carries ``deepagents-backends``.
_EXPECTED_EXTRAS = frozenset(
    {"acp", "desktop", "docker", "object-storage", "observability", "web-search-all"},
)


def _harness_agent_requirement() -> str:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    reqs = [
        dep
        for dep in data["project"]["dependencies"]
        if dep.split("[")[0].split(">")[0].split("=")[0].strip() == "orcakit-harness-agent"
    ]
    assert len(reqs) == 1, f"expected exactly one orcakit-harness-agent requirement, got {reqs}"
    return reqs[0]


def _declared_extras(requirement: str) -> frozenset[str]:
    _, _, rest = requirement.partition("[")
    extras, _, _ = rest.partition("]")
    return frozenset(part.strip() for part in extras.split(",") if part.strip())


def test_harness_agent_does_not_request_all_extra() -> None:
    """``[all]`` would re-enable the broken deepagents S3 backend from #780."""
    requirement = _harness_agent_requirement()
    extras = _declared_extras(requirement)
    assert "all" not in extras, (
        f"{requirement!r} requests the 'all' extra, which pulls deepagents-backends "
        "and breaks every S3 write/edit/ls (issue #780)"
    )


def test_harness_agent_does_not_request_remote_backends_extra() -> None:
    """``remote-backends`` is the extra that ships ``deepagents-backends``."""
    extras = _declared_extras(_harness_agent_requirement())
    assert "remote-backends" not in extras, (
        "the 'remote-backends' extra pulls deepagents-backends, whose S3 backend "
        "targets the deepagents 0.5/0.6 protocol (issue #780)"
    )


def test_harness_agent_still_requests_required_capabilities() -> None:
    """Narrowing the extra must not drop capabilities Octop depends on."""
    extras = _declared_extras(_harness_agent_requirement())
    missing = _EXPECTED_EXTRAS - extras
    assert not missing, f"orcakit-harness-agent requirement lost required extras: {sorted(missing)}"


def test_deepagents_backends_is_not_a_resolved_dependency() -> None:
    """Guards against re-introduction via another dependency or ``[all]``."""
    lock = _REPO / "uv.lock"
    if not lock.exists():  # pragma: no cover - wheel installs ship no lockfile
        pytest.skip("uv.lock not present")

    text = lock.read_text(encoding="utf-8")
    assert 'name = "deepagents-backends"' not in text, (
        "uv.lock resolves deepagents-backends; its S3 backend is incompatible with "
        "deepagents 0.7 and breaks s3/custom/oss/obs storage (issue #780)"
    )


def test_s3_backend_accepts_deepagents_write_result() -> None:
    """The backend harness actually builds for ``type=s3`` must write successfully.

    Rebuilds the exact failure of #780: a healthy backend returns a
    ``WriteResult`` populated only with the fields the installed deepagents
    protocol declares. This fails loudly if an incompatible implementation
    (such as ``deepagents_backends``) is re-introduced.
    """
    protocol = pytest.importorskip("deepagents.backends.protocol")
    harness_backends = pytest.importorskip("harness_agent.backends")

    write_result_fields = set(protocol.WriteResult.__dataclass_fields__)
    assert write_result_fields <= {"error", "path"}, (
        f"deepagents WriteResult shape changed: {sorted(write_result_fields)}"
    )

    spec = {
        "type": "s3",
        "bucket": "probe-bucket",
        "access_key_id": "ak",
        "secret_access_key": "sk",
        "endpoint_url": "https://s3.invalid",
    }
    try:
        backend = harness_backends.resolve_backend(spec, workspace_dir=".")
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - optional deps
        pytest.skip(f"s3 backend unavailable: {exc}")

    module = type(backend).__module__
    assert not module.startswith("deepagents_backends"), (
        f"resolve_backend picked {module}.{type(backend).__name__}, which targets the "
        "deepagents 0.5/0.6 protocol (issue #780)"
    )

    # ``ls`` is the sharpest probe: deepagents 0.7 renames it from ``ls_info``.
    assert type(backend).ls is not protocol.BackendProtocol.ls, (
        f"{module}.{type(backend).__name__} does not implement 'ls'; it inherits "
        "BackendProtocol's NotImplementedError stub, so directory browsing is broken"
    )
