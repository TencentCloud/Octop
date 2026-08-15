import { describe, expect, it } from "vitest";
import {
  canAccessPath,
  NAV_PERMISSIONS,
  pathPermissionKeys,
  PERM,
} from "../utils/permissions";
import { isWorkbenchPath } from "./index";

describe("pathPermissionKeys", () => {
  it("matches workbench and legacy aliases", () => {
    expect(isWorkbenchPath("/workbench")).toBe(true);
    expect(pathPermissionKeys("/workbench")).toEqual([...PERM.workbench]);
    expect(pathPermissionKeys("/workbench/terminal")).toEqual([
      ...PERM.terminal,
    ]);
    expect(pathPermissionKeys("/workbench/browser")).toEqual([...PERM.browser]);
    expect(pathPermissionKeys("/terminal")).toEqual([...PERM.terminal]);
    expect(pathPermissionKeys("/remote-browser")).toEqual([...PERM.browser]);
  });

  it("matches remote desktop and acp", () => {
    expect(pathPermissionKeys("/remote-desktop")).toEqual([...PERM.desktop]);
    expect(pathPermissionKeys("/acp")).toBe("admin");
  });

  it("keeps sso on users page, not advanced", () => {
    expect(pathPermissionKeys("/admin/users")).toEqual([...PERM.usersPage]);
    expect(pathPermissionKeys("/admin/advanced")).toEqual([
      ...PERM.advancedPage,
    ]);
    expect([...PERM.advancedPage]).not.toContain("sso");
    expect(NAV_PERMISSIONS["admin-users"]).toEqual(PERM.usersPage);
    expect(NAV_PERMISSIONS["admin-advanced"]).toEqual(PERM.advancedPage);
  });

  it("does not gate common pages", () => {
    expect(pathPermissionKeys("/chat")).toBeNull();
    expect(pathPermissionKeys("/experts")).toBeNull();
    expect(pathPermissionKeys("/tasks")).toBeNull();
    expect(pathPermissionKeys("/token-usage")).toBeNull();
    expect(pathPermissionKeys("/personalization/skills")).toBeNull();
  });

  it("gates settings modules", () => {
    expect(pathPermissionKeys("/connectors")).toEqual([...PERM.connectors]);
    expect(pathPermissionKeys("/skill-packages")).toEqual([
      ...PERM.skillPackages,
    ]);
    expect(pathPermissionKeys("/personalization/channels")).toEqual([
      ...PERM.channels,
    ]);
    expect(pathPermissionKeys("/knowledge-bases")).toEqual([
      ...PERM.knowledgeBasesPage,
    ]);
    expect([...PERM.advancedPage]).not.toContain("knowledge_settings");
  });

  it("canAccessPath respects holder permissions", () => {
    const user = { role: "user", permissions: ["desktop"] };
    expect(canAccessPath(user, "/remote-desktop")).toBe(true);
    expect(canAccessPath(user, "/admin/users")).toBe(false);
    expect(canAccessPath({ role: "admin", permissions: [] }, "/acp")).toBe(
      true,
    );
    expect(
      canAccessPath(
        { role: "user", permissions: ["knowledge_bases"] },
        "/knowledge-bases",
      ),
    ).toBe(true);
    expect(
      canAccessPath(
        { role: "user", permissions: ["knowledge_settings"] },
        "/knowledge-bases",
      ),
    ).toBe(true);
    expect(
      canAccessPath(
        { role: "user", permissions: ["knowledge_bases"] },
        "/admin/advanced",
      ),
    ).toBe(false);
  });
});
