"""Read OpenDesign's public sidecar status and canonical MCP registration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from octop.i18n import tr
from octop.infra.connectors.open_design import normalize_credentials

# Use the installed application's public SDK. Never read its private socket files,
# scan processes/ports, or guess a daemon URL. stdout stays server-side.
_DISCOVER = r"""
const {readFile} = await import('node:fs/promises');
const {pathToFileURL} = await import('node:url');
const path = await import('node:path');
const resources = process.argv[1];
const config = JSON.parse(await readFile(path.join(resources, 'open-design-config.json'), 'utf8'));
const load = name => import(pathToFileURL(path.join(resources, 'app/node_modules/@open-design', name, 'dist/index.mjs')).href);
const {getSidecarStatus} = await load('sidecar');
const {releaseChannelFromVersion} = await load('release');
for (const source of ['packaged', 'tools-pack']) {
  for (const mode of ['runtime', 'headless']) {
    const stamp = {app:'daemon', channel:releaseChannelFromVersion(config.appVersion) || 'stable', namespace:config.namespace, source, mode};
    const status = await getSidecarStatus(stamp, {timeoutMs:500}).catch(() => null);
    if (status?.state !== 'running' || !status.url) continue;
    const url = new URL(status.url);
    if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) continue;
    const response = await fetch(new URL('/api/mcp/install-info', url), {signal:AbortSignal.timeout(3000)});
    if (!response.ok) continue;
    const spec = await response.json();
    console.log(JSON.stringify(spec));
    process.exit(0);
  }
}
process.exit(1);
"""


def _installations() -> list[tuple[Path, Path]]:
    if sys.platform == "darwin":
        apps = [Path("/Applications/Open Design.app"), Path.home() / "Applications/Open Design.app"]
        return [(p / "Contents/MacOS/Open Design", p / "Contents/Resources") for p in apps]
    if sys.platform == "win32":
        bases = [Path(os.environ.get(k) or Path.home()) for k in ("LOCALAPPDATA", "ProgramFiles")]
        roots = [bases[0] / "Programs/Open Design", bases[1] / "Open Design"]
    else:
        roots = [Path("/opt/Open Design"), Path("/opt/open-design"), Path("/usr/lib/open-design")]
    return [
        (p / ("Open Design.exe" if sys.platform == "win32" else "open-design"), p / "resources")
        for p in roots
    ]


def detect_local_open_design() -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Read-only discovery; never launches the desktop or installs software."""
    installed = False
    found: list[dict[str, Any]] = []
    for binary, resources in _installations():
        if not binary.is_file():
            continue
        installed = True
        if not (resources / "open-design-config.json").is_file():
            continue
        try:
            result = subprocess.run(
                [str(binary), "--input-type=module", "-e", _DISCOVER, str(resources)],
                env={**os.environ, "ELECTRON_RUN_AS_NODE": "1"},
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            if result.returncode == 0:
                found.append(normalize_credentials(json.loads(result.stdout)))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    state = (
        "ready"
        if len(found) == 1
        else "multiple"
        if len(found) > 1
        else "stopped"
        if installed
        else "missing"
    )
    return {"installed": installed, "state": state}, found[0] if len(found) == 1 else None


def local_open_design_credentials() -> dict[str, Any]:
    status, credentials = detect_local_open_design()
    if credentials is None:
        raise ValueError(tr(f"connector.open_design.local_{status['state']}", "en"))
    return credentials
