import { describe, expect, it } from "vitest";
import { DEFERRED_FEATURES, resolveUiCapability } from "./capabilities";
import zh from "../locales/zh.json";
import en from "../locales/en.json";

describe("capability availability", () => {
  it("does not expose configuration to a user without permission", () => {
    expect(
      resolveUiCapability({
        permitted: false,
        configured: false,
        configurePath: "/admin/models",
      }),
    ).toEqual({
      state: "forbidden",
      reasonKey: "workbuddy.capability.forbidden",
    });
  });
  it("does not treat a missing implementation as missing configuration", () => {
    expect(
      resolveUiCapability({ supported: false, configured: false }),
    ).toEqual({
      state: "unsupported",
      reasonKey: "workbuddy.capability.unsupported",
    });
    expect(
      resolveUiCapability({
        configured: false,
        configurePath: "/admin/models",
      }),
    ).toEqual({
      state: "unconfigured",
      reasonKey: "workbuddy.capability.unconfigured",
      configurePath: "/admin/models",
    });
  });
  it("keeps deferred services separate from existing business routes and localizes every entry", () => {
    expect(new Set(DEFERRED_FEATURES.map((f) => f.path)).size).toBe(
      DEFERRED_FEATURES.length,
    );
    const existing = [
      "/chat",
      "/experts",
      "/tasks",
      "/knowledge-bases",
      "/admin/models",
    ];
    for (const feature of DEFERRED_FEATURES) {
      expect(existing).not.toContain(feature.path);
      for (const key of [feature.labelKey, feature.descriptionKey]) {
        const name = key.replace("workbuddy.", "") as keyof typeof zh.workbuddy;
        expect(typeof zh.workbuddy[name]).toBe("string");
        expect(typeof en.workbuddy[name]).toBe("string");
      }
    }
    expect(Object.keys(zh.workbuddy).sort()).toEqual(
      Object.keys(en.workbuddy).sort(),
    );
  });
});
