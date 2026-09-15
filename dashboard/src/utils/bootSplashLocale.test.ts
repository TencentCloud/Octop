import { afterEach, describe, expect, it, vi } from "vitest";
import indexHtml from "../../index.html?raw";
import { UI_LOCALE_STORAGE_KEY, type UiLocale } from "./localePrefs";

/**
 * The boot splash in ``index.html`` runs before any bundle is parsed, so it
 * cannot import from this module and duplicates the locale resolution inline.
 * These tests execute that inline block verbatim to keep the duplicate honest.
 */

const MARKER = "boot-splash-locale";

function extractBootScript(): string {
  const blocks = [...indexHtml.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(
    (match) => match[1],
  );
  const found = blocks.find((block) => block.includes(MARKER));
  if (!found) {
    throw new Error(
      `No inline <script> in index.html contains the ${MARKER} marker`,
    );
  }
  return found;
}

const bootScript = extractBootScript();

interface BootOptions {
  stored?: UiLocale | string;
  languages?: string[];
}

function runBootScript({ stored, languages = [] }: BootOptions) {
  document.documentElement.lang = "";
  document.body.innerHTML = '<div id="octop-boot-text">Loading…</div>';
  localStorage.clear();
  if (stored !== undefined) {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, stored);
  }
  vi.stubGlobal("navigator", {
    language: languages[0] ?? "",
    languages,
  });

  new Function(bootScript)();

  return {
    text: document.getElementById("octop-boot-text")?.textContent ?? "",
    lang: document.documentElement.lang,
  };
}

describe("boot splash locale", () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("uses the stored preference over an English browser (issue #685)", () => {
    const { text, lang } = runBootScript({
      stored: "zh",
      languages: ["en-US"],
    });
    expect(text).toBe("加载中…");
    expect(lang).toBe("zh-CN");
  });

  it("uses the stored preference over a Chinese browser", () => {
    const { text, lang } = runBootScript({
      stored: "en",
      languages: ["zh-CN"],
    });
    expect(text).toBe("Loading…");
    expect(lang).toBe("en");
  });

  it("falls back to the browser language when nothing is stored", () => {
    expect(runBootScript({ languages: ["zh-CN", "en-US"] }).text).toBe(
      "加载中…",
    );
    expect(runBootScript({ languages: ["en-US", "zh-CN"] }).text).toBe(
      "Loading…",
    );
  });

  it("falls back to English for unsupported or missing languages", () => {
    expect(runBootScript({ languages: ["fr-FR"] }).text).toBe("Loading…");
    expect(runBootScript({}).text).toBe("Loading…");
  });

  it("ignores a corrupt stored value and follows the browser", () => {
    expect(
      runBootScript({ stored: "not-a-locale", languages: ["zh-CN"] }).text,
    ).toBe("加载中…");
  });

  it("survives localStorage being unavailable", () => {
    const getItem = vi
      .spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => {
        throw new Error("localStorage disabled");
      });
    try {
      expect(runBootScript({ languages: ["zh-CN"] }).text).toBe("加载中…");
    } finally {
      getItem.mockRestore();
    }
  });
});
