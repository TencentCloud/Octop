import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const SRC = join(__dirname, "../..", "src");
const THEME_VARS = join(SRC, "styles/theme-vars.css");

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name === "node_modules" || name === "__tests__") continue;
      out.push(...walk(p));
    } else if (/\.(less|css|tsx|ts)$/.test(name) && !name.includes(".test.")) {
      out.push(p);
    }
  }
  return out;
}

function definedTokens(css: string): Set<string> {
  return new Set([...css.matchAll(/(--fn-[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
}

/**
 * GATE-2 (audit UI-2): every `var(--fn-*)` referenced outside the theme file
 * must resolve to a defined token, or carry a fallback. A var() naming an
 * undefined custom property with no fallback makes the declaration invalid at
 * computed-value time — the property silently resolves to unset, so cards
 * render transparent and error text inherits the parent colour.
 */
describe("design token integrity (theme-vars.css)", () => {
  const css = readFileSync(THEME_VARS, "utf-8");
  const defined = definedTokens(css);

  it("defines a non-empty token set", () => {
    expect(defined.size).toBeGreaterThan(100);
  });

  it("resolves every no-fallback var(--fn-…) reference in app code", () => {
    const broken: { file: string; token: string }[] = [];
    for (const file of walk(SRC)) {
      if (file === THEME_VARS) continue;
      const text = readFileSync(file, "utf-8");
      for (const m of text.matchAll(/var\(\s*(--fn-[a-z0-9-]+)\s*\)/g)) {
        if (!defined.has(m[1])) {
          broken.push({ file: relative(SRC, file), token: m[1] });
        }
      }
    }
    expect(
      broken,
      `undefined no-fallback var() uses: ${broken
        .map((b) => `${b.file}:${b.token}`)
        .join(", ")}`,
    ).toEqual([]);
  });

  it("defines the same alias set in light and dark blocks", () => {
    const light = css.slice(
      css.indexOf("LIGHT THEME"),
      css.indexOf("DARK THEME"),
    );
    const dark = css.slice(
      css.indexOf("DARK THEME"),
      css.indexOf("Brand palettes"),
    );
    const lightAliases = [
      ...light.matchAll(/^\s*(--fn-[a-z0-9-]+):\s*var\(--fn-/gm),
    ].map((m) => m[1]);
    const darkAliases = [
      ...dark.matchAll(/^\s*(--fn-[a-z0-9-]+):\s*var\(--fn-/gm),
    ].map((m) => m[1]);
    expect(new Set(darkAliases)).toEqual(new Set(lightAliases));
    expect(lightAliases.length).toBeGreaterThan(20);
  });
});
