import type { TFunction } from "i18next";
import type { DesktopStatus } from "./wails";

/**
 * Renders a shell status through the shell's i18next bundle. The Go side sends
 * only a copy key plus args (see desktop/src/status_codes.go); wording lives in
 * locales/{en,zh}.json under `desktopShell.`.
 */
export function statusText(t: TFunction, status: DesktopStatus): string {
  const args: Record<string, unknown> = { ...status.args };
  if (typeof args.seconds === "number") {
    args.wait = waitLabel(t, args.seconds);
  }
  return t(`desktopShell.${status.code}`, {
    ...args,
    defaultValue: status.code,
  });
}

function waitLabel(t: TFunction, seconds: number): string {
  const minutes = seconds % 60 === 0;
  const count = minutes ? seconds / 60 : seconds;
  return t(`desktopShell.wait.${minutes ? "minutes" : "seconds"}`, { count });
}
