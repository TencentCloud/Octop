"""OpenSandbox filesystem shim used until harness ships the helpers."""

from __future__ import annotations

import pytest

from octop.infra.backend.opensandbox_mkdir import install_opensandbox_fs


class _Result:
    def __init__(self, *, exit_code: int = 0, output: str = "") -> None:
        self.exit_code = exit_code
        self.output = output


def _backend() -> tuple[object, list[str]]:
    install_opensandbox_fs()
    from octop_harness.backends.opensandbox_sandbox import OpenSandbox

    seen: list[str] = []
    backend = OpenSandbox.__new__(OpenSandbox)
    backend.execute = lambda command: seen.append(command) or _Result()  # type: ignore[method-assign]
    return backend, seen


def test_mkdir_path_quotes_shell_metacharacters() -> None:
    backend, seen = _backend()
    backend.mkdir_path("/workspace/a b;rm -rf /")  # type: ignore[attr-defined]
    assert seen == ["mkdir -p '/workspace/a b;rm -rf /'"]


def test_delete_path_quotes_shell_metacharacters() -> None:
    backend, seen = _backend()
    backend.delete_path("/skills/a b;rm -rf /")  # type: ignore[attr-defined]
    assert seen == ["rm -rf '/skills/a b;rm -rf /'"]


def test_move_path_creates_parent_and_quotes() -> None:
    backend, seen = _backend()
    backend.move_path("/old;rm", "/new name/file;x")  # type: ignore[attr-defined]
    assert seen == ["mkdir -p '/new name' && mv '/old;rm' '/new name/file;x'"]


def test_nonzero_exit_raises() -> None:
    install_opensandbox_fs()
    from octop_harness.backends.opensandbox_sandbox import OpenSandbox

    backend = OpenSandbox.__new__(OpenSandbox)
    backend.execute = lambda _command: _Result(exit_code=1, output="denied")  # type: ignore[method-assign]
    with pytest.raises(OSError, match="denied"):
        backend.mkdir_path("/workspace/skills")  # type: ignore[attr-defined]


def test_install_does_not_replace_existing_helper() -> None:
    from octop_harness.backends.opensandbox_sandbox import OpenSandbox

    previous = getattr(OpenSandbox, "delete_path", None)

    def sentinel(self: object, path: str) -> None:
        del self, path

    OpenSandbox.delete_path = sentinel  # type: ignore[attr-defined]
    try:
        install_opensandbox_fs()
        assert OpenSandbox.delete_path is sentinel
    finally:
        if previous is None:
            del OpenSandbox.delete_path
        else:
            OpenSandbox.delete_path = previous  # type: ignore[attr-defined]
