import { describe, expect, it } from "vitest";
import {
  allowedSettingsSections,
  legacySettingsPath,
} from "./settingsRegistry";
import { MARKET_TABS, visibleMarketTabs } from "./marketModel";
import { buildNavSections } from "../layouts/sidebarNav";
const user = {
  id: 1,
  username: "operator",
  role: "user",
  permissions: ["providers", "captcha"],
  display_name: null,
  locale: "en",
};
describe("WorkBuddy navigation contracts", () => {
  it("shares exactly three market destinations and existing module permissions", () => {
    expect(MARKET_TABS.map((tab) => tab.id)).toEqual([
      "experts",
      "skills",
      "connectors",
    ]);
    expect(
      visibleMarketTabs(buildNavSections(user)).map((tab) => tab.id),
    ).toEqual(["experts", "skills"]);
  });
  it("gates settings by module rather than admin role", () => {
    const ids = allowedSettingsSections(user).map((item) => item.id);
    expect(ids).toContain("models");
    expect(ids).toContain("captcha");
    expect(ids).not.toContain("users");
    expect(ids).not.toContain("security");
  });
  it("preserves valid queries on settings aliases and maps installed skills", () => {
    expect(
      legacySettingsPath("/admin/models", "?tab=voice&source=bookmark"),
    ).toBe("/settings/models?tab=voice&source=bookmark");
    expect(legacySettingsPath("/personalization/skills", "?kind=custom")).toBe(
      "/skills?kind=custom&tab=installed",
    );
    expect(legacySettingsPath("/personalization/memory", "?tab=long")).toBe(
      "/settings/memory?tab=long",
    );
    expect(legacySettingsPath("/admin/advanced", "?tab=backup")).toBe(
      "/settings/backup?tab=backup",
    );
    expect(legacySettingsPath("/knowledge-bases", "")).toBeNull();
    expect(legacySettingsPath("/orca/admin/audit", "?source=bookmark")).toBe(
      "/settings/security?source=bookmark&tab=audit",
    );
    expect(legacySettingsPath("/octop/channels", "?agent=main")).toBe(
      "/settings/channels?agent=main",
    );
  });
});
