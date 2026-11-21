import assert from "node:assert/strict";
import { test } from "node:test";

import { compareVersions, isNewer, parseVersion } from "./version";

test("parseVersion strips leading v and splits triple", () => {
  assert.deepEqual(parseVersion("1.0.2"), { major: 1, minor: 0, patch: 2, pre: null });
  assert.deepEqual(parseVersion("v1.0.2"), { major: 1, minor: 0, patch: 2, pre: null });
  assert.deepEqual(parseVersion("1.0.3b1"), { major: 1, minor: 0, patch: 3, pre: "b1" });
  assert.equal(parseVersion("not-a-version"), null);
});

test("compareVersions orders release over its own prerelease", () => {
  assert.ok(compareVersions("1.0.3", "1.0.3b1") > 0);
  assert.ok(compareVersions("1.0.3b1", "1.0.2") > 0);
  assert.ok(compareVersions("1.0.2", "1.0.3b1") < 0);
  assert.equal(compareVersions("v1.0.2", "1.0.2"), 0);
});

test("compareVersions throws on unparseable input", () => {
  assert.throws(() => compareVersions("1.0", "1.0.2"));
});

test("isNewer is strict", () => {
  assert.equal(isNewer("1.0.3b1", "1.0.2"), true);
  assert.equal(isNewer("1.0.2", "1.0.2"), false);
});
