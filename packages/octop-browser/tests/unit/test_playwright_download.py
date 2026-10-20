"""Tests for Playwright CDN source race."""

from __future__ import annotations

from octop_browser.playwright_download import (
    DOWNLOAD_HOST_ENV,
    PLAYWRIGHT_CDN_MIRROR,
    PLAYWRIGHT_CDN_OFFICIAL,
    DownloadCandidate,
    build_download_candidates,
    env_for_candidate,
    plain_cli_env,
    race_download_sources,
)


def test_candidates_are_mirror_then_official(monkeypatch) -> None:
    monkeypatch.delenv(DOWNLOAD_HOST_ENV, raising=False)
    cands = build_download_candidates()
    assert [c.kind for c in cands] == ["npmmirror", "official"]
    assert cands[0].host == PLAYWRIGHT_CDN_MIRROR
    assert cands[0].probe_url == f"{PLAYWRIGHT_CDN_MIRROR}/"
    assert cands[1].host == ""
    assert cands[1].probe_url == f"{PLAYWRIGHT_CDN_OFFICIAL}/"


def test_custom_host_is_prepended_and_not_duplicated(monkeypatch) -> None:
    monkeypatch.setenv(DOWNLOAD_HOST_ENV, PLAYWRIGHT_CDN_MIRROR)
    cands = build_download_candidates()
    assert [c.kind for c in cands] == ["custom", "official"]
    assert cands[0].host == PLAYWRIGHT_CDN_MIRROR


def test_official_alias_is_not_added_as_custom(monkeypatch) -> None:
    monkeypatch.setenv(DOWNLOAD_HOST_ENV, PLAYWRIGHT_CDN_OFFICIAL)
    cands = build_download_candidates()
    assert [c.kind for c in cands] == ["npmmirror", "official"]


def test_race_orders_by_ttfb_and_skips_failures() -> None:
    cands = [
        DownloadCandidate(
            kind="official",
            host="",
            probe_url="http://official",
        ),
        DownloadCandidate(
            kind="npmmirror",
            host=PLAYWRIGHT_CDN_MIRROR,
            probe_url="http://mirror",
        ),
    ]

    def probe(url: str, timeout_s: float) -> float:
        if url.endswith("official"):
            raise TimeoutError("official blocked")
        return 0.12

    ranked = race_download_sources(cands, probe=probe)
    assert [c.kind for c in ranked] == ["npmmirror"]


def test_race_keeps_catalog_order_when_all_probes_fail() -> None:
    cands = [
        DownloadCandidate(
            kind="npmmirror",
            host=PLAYWRIGHT_CDN_MIRROR,
            probe_url="http://mirror",
        ),
        DownloadCandidate(
            kind="official",
            host="",
            probe_url="http://official",
        ),
    ]

    def probe(_url: str, _timeout_s: float) -> float:
        raise OSError("offline")

    ranked = race_download_sources(cands, probe=probe)
    assert [c.kind for c in ranked] == ["npmmirror", "official"]


def test_env_for_candidate_sets_or_clears_host(monkeypatch) -> None:
    monkeypatch.setenv(DOWNLOAD_HOST_ENV, "https://stale.example")
    mirror = DownloadCandidate(
        kind="npmmirror",
        host=PLAYWRIGHT_CDN_MIRROR,
        probe_url=f"{PLAYWRIGHT_CDN_MIRROR}/",
    )
    env = env_for_candidate(mirror)
    assert env[DOWNLOAD_HOST_ENV] == PLAYWRIGHT_CDN_MIRROR
    assert env["NO_COLOR"] == "1"
    assert env["FORCE_COLOR"] == "0"
    assert env["NODE_DISABLE_COLORS"] == "1"

    official = DownloadCandidate(kind="official", host="", probe_url="http://x")
    env = env_for_candidate(official)
    assert DOWNLOAD_HOST_ENV not in env
    assert env["NO_COLOR"] == "1"


def test_plain_cli_env_overrides_forced_color(monkeypatch) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    env = plain_cli_env()
    assert env["NO_COLOR"] == "1"
    assert env["FORCE_COLOR"] == "0"
    assert env["NODE_DISABLE_COLORS"] == "1"
