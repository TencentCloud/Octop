"""CPU architecture checks used by the Docker live boot test."""

from __future__ import annotations

from pathlib import Path

import pytest

_ARCH_ALIASES = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "x86_64": "amd64",
    "amd64": "amd64",
}


def normalized_cpu_arch(value: str) -> str:
    """Collapse uname and Docker names for the same CPU."""
    key = value.strip().lower()
    return _ARCH_ALIASES.get(key, key)


def native_import_failed(code: int, text: str) -> bool:
    """True when a containerized import died with SIGILL (exit 132)."""
    if code == 132:
        return True
    return "illegal instruction" in text.lower()


def test_arm_uname_matches_docker_arm64() -> None:
    assert normalized_cpu_arch("aarch64") == normalized_cpu_arch("arm64")


def test_amd64_uname_matches_docker_amd64() -> None:
    assert normalized_cpu_arch("x86_64") == normalized_cpu_arch("amd64")


def test_arm_does_not_match_amd64() -> None:
    assert normalized_cpu_arch("aarch64") != normalized_cpu_arch("x86_64")


@pytest.mark.parametrize(
    "code, text",
    [
        (132, ""),
        (1, "Illegal instruction (core dumped)"),
    ],
)
def test_sigill_failure_is_recognized(code: int, text: str) -> None:
    assert native_import_failed(code, text)


def test_clean_import_is_not_sigill() -> None:
    assert not native_import_failed(0, "")


def test_docker_publish_still_builds_arm64() -> None:
    """ARM NAS uses the same tag; dropping arm64 from CI is how that image disappears."""
    root = Path(__file__).resolve().parents[2]
    text = (root / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
    assert "linux/arm64" in text
    assert "ubuntu-24.04-arm" in text
    assert "ARM image missing" in text
    boot = text.index("test_docker_image_runs_on_this_cpu_and_stays_disabled")
    push = text.index('docker push "$tag"')
    assert boot < push
    assert "load: true" in text
    assert "fail-fast: false" in text
