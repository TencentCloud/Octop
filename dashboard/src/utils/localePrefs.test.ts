import { afterEach, describe, expect, it, vi } from "vitest";
import {
  detectBrowserLocale,
  normalizeUiLocale,
  readStoredUiLocale,
  resolveInitialLocale,
  speechLocaleFromUi,
  storeUiLocale,
  UI_LOCALE_STORAGE_KEY,
} from "./localePrefs";

describe("localePrefs", () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("detectBrowserLocale prefers zh when browser lists Chinese first", () => {
    vi.stubGlobal("navigator", {
      language: "en-US",
      languages: ["zh-CN", "en-US"],
    });
    expect(detectBrowserLocale()).toBe("zh");
  });

  it("detectBrowserLocale prefers en when browser lists English first", () => {
    vi.stubGlobal("navigator", {
      language: "zh-CN",
      languages: ["en-US", "zh-CN"],
    });
    expect(detectBrowserLocale()).toBe("en");
  });

  it("detectBrowserLocale detects Japanese", () => {
    vi.stubGlobal("navigator", {
      language: "ja-JP",
      languages: ["ja-JP", "en-US"],
    });
    expect(detectBrowserLocale()).toBe("ja");
  });

  it("normalizeUiLocale keeps ja and maps unknown tags to en", () => {
    expect(normalizeUiLocale("ja")).toBe("ja");
    expect(normalizeUiLocale("ja-JP")).toBe("ja");
    expect(normalizeUiLocale("fr")).toBe("en");
    expect(normalizeUiLocale(null)).toBe("zh");
  });

  it("stored ja preference round-trips", () => {
    storeUiLocale("ja");
    expect(readStoredUiLocale()).toBe("ja");
  });

  it("resolveInitialLocale uses stored preference over browser", () => {
    vi.stubGlobal("navigator", {
      language: "en-US",
      languages: ["en-US"],
    });
    storeUiLocale("zh");
    expect(resolveInitialLocale()).toBe("zh");
    expect(readStoredUiLocale()).toBe("zh");
    localStorage.removeItem(UI_LOCALE_STORAGE_KEY);
    expect(resolveInitialLocale()).toBe("en");
  });

  it("speechLocaleFromUi maps UI locale to STT BCP-47 tags", () => {
    expect(speechLocaleFromUi("zh")).toBe("zh-CN");
    expect(speechLocaleFromUi("zh-CN")).toBe("zh-CN");
    expect(speechLocaleFromUi("en")).toBe("en-US");
    expect(speechLocaleFromUi("en-US")).toBe("en-US");
    expect(speechLocaleFromUi("ja")).toBe("ja-JP");
    expect(speechLocaleFromUi(null)).toBe("zh-CN");
  });
});
