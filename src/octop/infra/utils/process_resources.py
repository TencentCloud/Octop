"""Process resource defaults shared by service installers and direct starts."""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

NOFILE_TARGET = 65535


def ensure_nofile_limit() -> None:
    """Raise only the soft fd limit, within the inherited hard limit.

    Docker and direct CLI starts do not use the systemd/launchd limits.
    A denied adjustment must not prevent startup; report the actual limits
    so operators can fix the container or service configuration.
    """
    if sys.platform == "win32":
        return

    import resource

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError):
        logger.warning("Could not read file descriptor limits", exc_info=True)
        return

    target = NOFILE_TARGET if hard == resource.RLIM_INFINITY else min(NOFILE_TARGET, hard)
    if soft != resource.RLIM_INFINITY and soft < target:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            soft = target
        except (OSError, ValueError):
            logger.warning(
                "Could not raise file descriptor soft limit from %s to %s",
                soft,
                target,
                exc_info=True,
            )

    logger.info("File descriptor limits: soft=%s hard=%s", soft, hard)
    if soft != resource.RLIM_INFINITY and soft < NOFILE_TARGET:
        logger.warning(
            "File descriptor soft limit is only %s; configure the container/service NOFILE limit to at least %s",
            soft,
            NOFILE_TARGET,
        )
