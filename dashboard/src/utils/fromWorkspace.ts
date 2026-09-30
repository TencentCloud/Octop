/**
 * SEC-2 durable fix: the ``from_workspace`` query parameter was removed from
 * the workspace I/O HTTP surface — paths always resolve workspace-relative
 * (leading ``/`` = workspace root). This helper is kept as a pass-through so
 * existing call sites keep compiling; new code should not use it.
 */
export const FROM_WORKSPACE_QS = "from_workspace=true";

/** No-op: the parameter no longer exists on the API. Kept for call-site
 * compatibility; will be removed in a follow-up cleanup. */
export function withFromWorkspace(url: string): string {
  return url;
}
