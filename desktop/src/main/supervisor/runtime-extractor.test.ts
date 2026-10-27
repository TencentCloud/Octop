import assert from "node:assert/strict";
import { test } from "node:test";

import { classifyRuntime } from "./runtime-extractor";
import { compareVersions } from "./version";

const cmp = compareVersions;

test("classifyRuntime: first run extracts", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: null, interpreterExists: false },
    cmp,
  );
  assert.deepEqual(d, { action: "extract", reason: "first-run" });
});

test("classifyRuntime: unparseable local version replaces", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: null, interpreterExists: true },
    cmp,
  );
  assert.equal(d.action, "replace");
});

test("classifyRuntime: same version with interpreter skips", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: "1.0.2", interpreterExists: true },
    cmp,
  );
  assert.deepEqual(d, { action: "skip", reason: "up-to-date" });
});

test("classifyRuntime: same version missing interpreter replaces", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: "1.0.2", interpreterExists: false },
    cmp,
  );
  assert.deepEqual(d, { action: "replace", reason: "corrupt" });
});

test("classifyRuntime: local lower replaces", () => {
  const d = classifyRuntime(
    { version: "1.0.3", sha256: "x" },
    { version: "1.0.2", interpreterExists: true },
    cmp,
  );
  assert.deepEqual(d, { action: "replace", reason: "older" });
});

test("classifyRuntime: local higher stops (manual downgrade)", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: "1.0.3", interpreterExists: true },
    cmp,
  );
  assert.deepEqual(d, { action: "stop", reason: "local-newer", localVersion: "1.0.3" });
});
