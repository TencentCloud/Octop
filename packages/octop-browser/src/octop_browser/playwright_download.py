"""Race Playwright CDN mirrors, then download from the winner."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

PLAYWRIGHT_CDN_OFFICIAL = "https://cdn.playwright.dev"
PLAYWRIGHT_CDN_MIRROR = "https://cdn.npmmirror.com/binaries/playwright"
DOWNLOAD_HOST_ENV = "PLAYWRIGHT_DOWNLOAD_HOST"

_PROBE_TIMEOUT_S = 4.0
_OFFICIAL_HOST_ALIASES = frozenset(
    {
        PLAYWRIGHT_CDN_OFFICIAL,
        "https://cdn.playwright.dev/dbazure/download/playwright",
        "https://playwright.download.prss.microsoft.com/dbazure/download/playwright",
    }
)


@dataclass(frozen=True)
class DownloadCandidate:
    """One Playwright download host that can be probed then used."""

    kind: str
    host: str
    probe_url: str


ProbeFn = Callable[[str, float], float]


def _normalize_host(raw: str) -> str:
    return raw.strip().rstrip("/")


def build_download_candidates() -> list[DownloadCandidate]:
    """Build custom (if set) + npmmirror + official Playwright CDN candidates."""
    candidates: list[DownloadCandidate] = []
    seen: set[str] = set()

    custom = _normalize_host(os.environ.get(DOWNLOAD_HOST_ENV, ""))
    if custom and custom not in _OFFICIAL_HOST_ALIASES:
        candidates.append(
            DownloadCandidate(
                kind="custom",
                host=custom,
                probe_url=f"{custom}/",
            )
        )
        seen.add(custom)

    mirror = _normalize_host(PLAYWRIGHT_CDN_MIRROR)
    if mirror not in seen:
        candidates.append(
            DownloadCandidate(
                kind="npmmirror",
                host=mirror,
                probe_url=f"{mirror}/",
            )
        )
        seen.add(mirror)

    candidates.append(
        DownloadCandidate(
            kind="official",
            host="",
            probe_url=f"{PLAYWRIGHT_CDN_OFFICIAL}/",
        )
    )
    return candidates


def probe_source(url: str, timeout_s: float = _PROBE_TIMEOUT_S) -> float:
    """Return TTFB in seconds for a 1 KiB range GET. Raises on network/5xx."""
    started = time.monotonic()
    req = Request(
        url,
        headers={"Range": "bytes=0-1023"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            _ = resp.read(16)
            status = int(getattr(resp, "status", 200))
            if status >= 500:
                raise OSError(f"HTTP {status}")
    except HTTPError as exc:
        if exc.fp is not None:
            try:
                _ = exc.read(16)
            except OSError:
                pass
        if exc.code >= 500:
            raise
    return time.monotonic() - started


def race_download_sources(
    candidates: list[DownloadCandidate],
    *,
    probe: ProbeFn = probe_source,
    timeout_s: float = _PROBE_TIMEOUT_S,
) -> list[DownloadCandidate]:
    """Probe candidates in parallel and return them fastest-first.

    Failed probes are omitted. If every probe fails, the original candidate
    order is returned so the caller can still attempt a full download.
    """
    if not candidates:
        return []
    ranked: list[tuple[float, DownloadCandidate]] = []
    workers = min(len(candidates), 3)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(probe, cand.probe_url, timeout_s): cand for cand in candidates
        }
        for fut in as_completed(futures):
            cand = futures[fut]
            try:
                ttfb = fut.result()
            except Exception as exc:  # pylint: disable=broad-except
                logger.info("Playwright CDN probe failed (%s): %s", cand.kind, exc)
                continue
            if ttfb < 0:
                continue
            ranked.append((ttfb, cand))
    ranked.sort(key=lambda item: item[0])
    if not ranked:
        logger.info("Playwright CDN probes all failed; falling back to catalog order")
        return list(candidates)
    winner = ranked[0][1]
    logger.info(
        "Playwright CDN race winner=%s ttfb=%.3fs (n=%d)",
        winner.kind,
        ranked[0][0],
        len(ranked),
    )
    return [item[1] for item in ranked]


def plain_cli_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Copy *env* (or ``os.environ``) and tell child CLIs not to emit ANSI.

    Playwright's Node installer wraps the zip name in bold
    (``ESC[1mlinux64.zipESC[22m``). Chalk and Node ``util.styleText`` honor
    ``NO_COLOR`` / ``FORCE_COLOR=0`` / ``NODE_DISABLE_COLORS``.
    """
    out = os.environ.copy() if env is None else dict(env)
    out["NO_COLOR"] = "1"
    out["FORCE_COLOR"] = "0"
    out["NODE_DISABLE_COLORS"] = "1"
    return out


def env_for_candidate(cand: DownloadCandidate) -> dict[str, str]:
    """Copy process env with ``PLAYWRIGHT_DOWNLOAD_HOST`` set for *cand*."""
    env = os.environ.copy()
    if cand.host:
        env[DOWNLOAD_HOST_ENV] = cand.host
    else:
        env.pop(DOWNLOAD_HOST_ENV, None)
    return plain_cli_env(env)
