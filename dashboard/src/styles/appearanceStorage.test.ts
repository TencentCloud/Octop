import { afterEach, describe, expect, it } from "vitest";
import {
  loadAppearanceOnBoot,
  readStoredAppearance,
  writeStoredAppearance,
} from "./appearanceStorage";
import {
  DEFAULT_PALETTE,
  LEGACY_PALETTE_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from "./themePalettes";

afterEach(() => {
  localStorage.removeItem(THEME_STORAGE_KEY);
  localStorage.removeItem(LEGACY_PALETTE_STORAGE_KEY);
});

describe("appearanceStorage", () => {
  it("defaults to system preference and rose palette", () => {
    expect(readStoredAppearance()).toEqual({
      preference: "system",
      palette: DEFAULT_PALETTE,
    });
  });

  it("migrates legacy plain theme string + palette key", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    localStorage.setItem(LEGACY_PALETTE_STORAGE_KEY, "tech");

    expect(readStoredAppearance()).toEqual({
      preference: "dark",
      palette: "tech",
    });
  });

  it("reads unified JSON under the theme key", () => {
    localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({ preference: "light", palette: "indigo" }),
    );

    expect(readStoredAppearance()).toEqual({
      preference: "light",
      palette: "indigo",
    });
  });

  it("writes preference and palette as different fields in the same key", () => {
    writeStoredAppearance({ preference: "system", palette: "teal" });
    localStorage.setItem(LEGACY_PALETTE_STORAGE_KEY, "should-be-removed");

    writeStoredAppearance({ preference: "light", palette: "violet" });

    expect(localStorage.getItem(LEGACY_PALETTE_STORAGE_KEY)).toBeNull();
    expect(JSON.parse(localStorage.getItem(THEME_STORAGE_KEY)!)).toEqual({
      preference: "light",
      palette: "violet",
    });
  });

  it("loadAppearanceOnBoot migrates legacy keys into unified JSON", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    localStorage.setItem(LEGACY_PALETTE_STORAGE_KEY, "amber");

    expect(loadAppearanceOnBoot()).toEqual({
      preference: "dark",
      palette: "amber",
    });
    expect(localStorage.getItem(LEGACY_PALETTE_STORAGE_KEY)).toBeNull();
    expect(JSON.parse(localStorage.getItem(THEME_STORAGE_KEY)!)).toEqual({
      preference: "dark",
      palette: "amber",
    });
  });

  it("falls back safely on invalid JSON or unknown values", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "{not-json");
    expect(readStoredAppearance()).toEqual({
      preference: "system",
      palette: DEFAULT_PALETTE,
    });

    localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({ preference: "neon", palette: "pink" }),
    );
    expect(readStoredAppearance()).toEqual({
      preference: "system",
      palette: DEFAULT_PALETTE,
    });
  });
});
