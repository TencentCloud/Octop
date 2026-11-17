import assert from "node:assert/strict";
import { test } from "node:test";

import { resolveAppVersion } from "./app-version";

/**
 * `package.json` holds a local placeholder, so it must never win over the
 * bundled manifest or the dev runtime: a wrong product version makes every
 * release look newer than the running install (§6.1) and points the extraction
 * step at a zip name that does not exist (§2.3).
 */

const pkg = (value: string) => (): string => value;

test("prefers the bundled portable manifest in a packaged build", async () => {
  const version = await resolveAppVersion({
    readBundled: async () => "1.0.3b1",
    readDevRuntime: async () => "0.0.0-dev",
    readPackage: pkg("0.1.0"),
  });
  assert.equal(version, "1.0.3b1");
});

test("falls back to the dev runtime when no portable is bundled", async () => {
  const version = await resolveAppVersion({
    readBundled: async () => {
      throw new Error("ENOENT: portable-version.json");
    },
    readDevRuntime: async () => "1.0.3b1",
    readPackage: pkg("0.1.0"),
  });
  assert.equal(version, "1.0.3b1");
});

test("falls back to package.json when nothing else resolves", async () => {
  const version = await resolveAppVersion({
    readBundled: async () => null,
    readDevRuntime: async () => null,
    readPackage: pkg("0.1.0"),
  });
  assert.equal(version, "0.1.0");
});

test("ignores blank versions instead of returning an empty string", async () => {
  // An empty product version would compare as older than every release.
  const version = await resolveAppVersion({
    readBundled: async () => "   ",
    readDevRuntime: async () => "",
    readPackage: pkg("0.1.0"),
  });
  assert.equal(version, "0.1.0");
});

test("trims surrounding whitespace from the manifest value", async () => {
  const version = await resolveAppVersion({
    readBundled: async () => " 1.0.3b1\n",
    readDevRuntime: async () => null,
    readPackage: pkg("0.1.0"),
  });
  assert.equal(version, "1.0.3b1");
});
