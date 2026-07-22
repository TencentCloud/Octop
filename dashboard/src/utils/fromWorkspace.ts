/** Query flag for agent workspace UI: leading ``/`` is workspace-relative. */
export const FROM_WORKSPACE_QS = "from_workspace=true";

/** Append ``from_workspace=true`` to an agent workspace API URL. */
export function withFromWorkspace(url: string): string {
  if (url.includes("from_workspace=")) return url;
  return url.includes("?")
    ? `${url}&${FROM_WORKSPACE_QS}`
    : `${url}?${FROM_WORKSPACE_QS}`;
}
