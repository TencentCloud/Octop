/**
 * Locale bundle invariants.
 *
 * Guards against the dictionaries drifting apart again:
 *   1. ``en.json`` and ``zh.json`` expose exactly the same key set, so neither
 *      locale can silently fall back to raw keys or inline defaults.
 *   2. English values must not contain CJK characters — the only exception is
 *      ``account.langZh``, the intentional native name in the language picker.
 */

import { describe, expect, it } from "vitest";
import en from "./en.json";
import zh from "./zh.json";

const CJK = /[\u4e00-\u9fff]/;
const CJK_ALLOWLIST = new Set(["account.langZh"]);

function flatten(value: unknown, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object") {
      Object.assign(out, flatten(child, path));
    } else if (typeof child === "string") {
      out[path] = child;
    }
  }
  return out;
}

describe("locale bundles", () => {
  it("en and zh expose exactly the same key set", () => {
    const enKeys = Object.keys(flatten(en)).sort();
    const zhKeys = Object.keys(flatten(zh)).sort();
    expect(zhKeys).toEqual(enKeys);
  });

  it("english values contain no CJK outside the allowlist", () => {
    const offenders = Object.entries(flatten(en))
      .filter(([key, value]) => CJK.test(value) && !CJK_ALLOWLIST.has(key))
      .map(([key]) => key);
    expect(offenders).toEqual([]);
  });
});
