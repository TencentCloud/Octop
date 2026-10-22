/** Map workspace tree entry path to dashboard `/…` form for API calls. */
export function workspaceEntryPath(infoPath: string): string {
  if (infoPath.startsWith("/")) return infoPath;
  const normalized = infoPath.replace(/\\/g, "/").replace(/^\/+/, "");
  return normalized ? `/${normalized}` : "/";
}

/**
 * Normalize a tool-reported path into a workspace-relative fragment that the
 * workspace file API expects.
 *
 * Harness file tools may report an on-disk absolute path such as
 * ``/home/wally/.octop/agents/main/hello.py`` (or ``/workspace/hello.py`` on a
 * container where the workspace dir *is* ``/workspace``). The workspace viewer
 * always passes a relative path like ``/hello.py``; collapse absolute forms to
 * the same shape so the chat file box opens them instead of 404-ing.
 *
 * Returns the input unchanged when it is already relative or matches no known
 * layout, so non-workspace absolute paths fall through as before.
 */
export function toWorkspaceRelativePath(raw: string, agentId: string): string {
  if (!raw) return raw;
  let p = raw
    .trim()
    .replace(/\\/g, "/")
    .replace(/^file:\/\//i, "");

  // New agents use /.agentbuddy/; legacy ones keep /.octop/.
  const agentMarkers = [
    `/.octop/agents/${agentId.toLowerCase()}/`,
    `/.agentbuddy/agents/${agentId.toLowerCase()}/`,
  ];
  const lower = p.toLowerCase();
  let matched = -1;
  let markerLen = 0;
  for (const marker of agentMarkers) {
    const idx = lower.lastIndexOf(marker);
    if (idx > matched) {
      matched = idx;
      markerLen = marker.length;
    }
  }
  if (matched >= 0) {
    p = p.slice(matched + markerLen);
  } else if (p === "/workspace") {
    p = "";
  } else if (p.includes("/workspace/")) {
    p = p.slice(p.lastIndexOf("/workspace/") + "/workspace/".length);
  } else if (p.startsWith("/workspace")) {
    p = p.slice("/workspace".length);
  }

  const rel = p.replace(/^\/+/, "");
  return rel ? `/${rel}` : "/";
}
