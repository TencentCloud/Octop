import { describe, expect, it } from "vitest";
import {
  shouldJumpToChromeInstall,
  WORKBENCH_BROWSER_PATH,
} from "./chromeInstallGate";

describe("shouldJumpToChromeInstall", () => {
  it("redirects when browsers_ok is missing or false", () => {
    expect(shouldJumpToChromeInstall({})).toBe(true);
    expect(shouldJumpToChromeInstall({ browsers_ok: false })).toBe(true);
  });

  it("stays in chat when Chrome is available", () => {
    expect(shouldJumpToChromeInstall({ browsers_ok: true })).toBe(false);
  });

  it("points at the workbench browser tab", () => {
    expect(WORKBENCH_BROWSER_PATH).toBe("/workbench/browser");
  });
});
