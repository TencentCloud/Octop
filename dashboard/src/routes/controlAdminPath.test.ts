import { describe, expect, it } from "vitest";
import { isControlAdminPath, isWorkbenchPath } from "./index";

describe("isControlAdminPath", () => {
  it("matches workbench and legacy aliases", () => {
    expect(isWorkbenchPath("/workbench")).toBe(true);
    expect(isControlAdminPath("/workbench")).toBe(true);
    expect(isControlAdminPath("/workbench/terminal")).toBe(true);
    expect(isControlAdminPath("/workbench/browser")).toBe(true);
    expect(isControlAdminPath("/terminal")).toBe(true);
    expect(isControlAdminPath("/remote-browser")).toBe(true);
  });

  it("matches remote desktop and acp", () => {
    expect(isControlAdminPath("/remote-desktop")).toBe(true);
    expect(isControlAdminPath("/acp")).toBe(true);
  });

  it("does not match settings or common pages", () => {
    expect(isControlAdminPath("/chat")).toBe(false);
    expect(isControlAdminPath("/connectors")).toBe(false);
    expect(isControlAdminPath("/personalization/skills")).toBe(false);
    expect(isControlAdminPath("/skill-packages")).toBe(false);
    expect(isControlAdminPath("/admin/users")).toBe(false);
  });
});
