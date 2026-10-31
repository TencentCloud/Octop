"""Runtime images must ship Node.js for skills that call node / npm / npx."""

from __future__ import annotations

from pathlib import Path


def test_images_ship_nodejs_runtime() -> None:
    """Both Dockerfiles copy Node 20 from the frontend stage into the runtime.

    Published FnOS Docker packages pull the image built from docker/Dockerfile.
    The FnOS source Dockerfile must keep the same runtime so a manual build
    does not drop Node.
    """
    repo = Path(__file__).resolve().parents[2]
    for rel in ("docker/Dockerfile", "fnos/docker/Dockerfile"):
        text = (repo / rel).read_text(encoding="utf-8")
        assert "COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node" in text
        assert (
            "COPY --from=frontend-builder /usr/local/lib/node_modules /usr/local/lib/node_modules"
            in text
        )
        assert "ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm" in text
        assert "ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx" in text
        assert "node --version" in text
        assert "npm --version" in text
        assert "npx --version" in text
