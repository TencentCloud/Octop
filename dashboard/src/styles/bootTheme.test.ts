import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { THEME_STORAGE_KEY } from "./themePalettes";

const INDEX_HTML = readFileSync(resolve(__dirname, "../../index.html"), "utf8");

function bootThemeScript(): string {
  const match = INDEX_HTML.match(
    /<script id="octop-boot-theme">([\s\S]*?)<\/script>/,
  );
  if (!match) {
    throw new Error("octop-boot-theme script missing from index.html");
  }
  return match[1];
}

function stubMatchMedia(systemDark: boolean): void {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("prefers-color-scheme: dark") ? systemDark : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

describe("index.html boot theme", () => {
  const originalMatchMedia = window.matchMedia;

  beforeEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY);
    document.documentElement.removeAttribute("data-theme");
    stubMatchMedia(true);
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    localStorage.removeItem(THEME_STORAGE_KEY);
    document.documentElement.removeAttribute("data-theme");
  });

  it("styles the splash from data-theme, not OS color scheme", () => {
    expect(INDEX_HTML).toContain('html[data-theme="dark"] #octop-boot');
    expect(INDEX_HTML).not.toMatch(
      /@media \(prefers-color-scheme: dark\)[\s\S]*#octop-boot/,
    );
  });

  it("uses the white vertical mark in dark mode", () => {
    expect(INDEX_HTML).toContain('src="/logo_vertical_white.svg"');
    expect(INDEX_HTML).toContain(
      'html[data-theme="dark"] .octop-boot-logo--dark',
    );
  });

  it("keeps a stored light preference over OS dark", () => {
    localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({ preference: "light", palette: "rose" }),
    );
    eval(bootThemeScript());
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("honors a stored dark preference", () => {
    stubMatchMedia(false);
    localStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({ preference: "dark", palette: "rose" }),
    );
    eval(bootThemeScript());
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("follows the OS when preference is system or missing", () => {
    eval(bootThemeScript());
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    document.documentElement.removeAttribute("data-theme");
    stubMatchMedia(false);
    eval(bootThemeScript());
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("migrates a legacy plain theme string", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    eval(bootThemeScript());
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
