/** Workbench tab that hosts Playwright Chromium install. */
export const WORKBENCH_BROWSER_PATH = "/workbench/browser";

/** Host has no launchable Chrome/Chromium (`GET /browser/env-status`). */
export function shouldJumpToChromeInstall(env: {
  browsers_ok?: boolean;
}): boolean {
  return env.browsers_ok !== true;
}
