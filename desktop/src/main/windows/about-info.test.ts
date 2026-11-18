import assert from "node:assert/strict";
import { test } from "node:test";

import {
  formatAboutDate,
  formatAboutDetail,
  formatAboutOs,
  resolveGitStamp,
  windowsInstallScope,
} from "./about-info";

test("per-user and per-machine installs are named, dev electron is not", () => {
  assert.equal(windowsInstallScope("C:\\Users\\finn\\Octop\\Octop.exe"), "user");
  assert.equal(windowsInstallScope("C:\\Program Files\\Octop\\Octop.exe"), "system");
  assert.equal(
    windowsInstallScope("D:\\repo\\Octop\\desktop\\src\\node_modules\\electron\\dist\\electron.exe"),
    null,
  );
});

test("about date is UTC without milliseconds", () => {
  assert.equal(formatAboutDate("2026-10-27T20:18:03Z"), "2026-10-27T20:18:03Z");
  assert.equal(formatAboutDate("2026-10-28T04:18:03+08:00"), "2026-10-27T20:18:03Z");
  assert.equal(formatAboutDate(""), "");
  assert.equal(formatAboutDate("not-a-date"), "not-a-date");
});

test("about detail lists the runtime the way a desktop about box does", () => {
  assert.equal(
    formatAboutDetail({
      version: "1.0.3b1",
      setup: "user",
      commit: "2c33b50b16c472efe58357d1d2a8a5414bc23fbf",
      date: "2026-10-27T20:18:03Z",
      electron: "43.8.3",
      chromium: "150.0.7871.250",
      node: "24.22.1",
      v8: "15.0.245.31-electron.0",
      os: formatAboutOs("Windows_NT", "x64", "10.0.26300"),
    }),
    [
      "Version: 1.0.3b1 (user setup)",
      "Commit: 2c33b50b16c472efe58357d1d2a8a5414bc23fbf",
      "Date: 2026-10-27T20:18:03Z",
      "Electron: 43.8.3",
      "Chromium: 150.0.7871.250",
      "Node.js: 24.22.1",
      "V8: 15.0.245.31-electron.0",
      "OS: Windows_NT x64 10.0.26300",
    ].join("\n"),
  );
});

test("missing commit and date are left out", () => {
  const detail = formatAboutDetail({
    version: "1.0.3b1",
    setup: null,
    commit: "",
    date: "  ",
    electron: "45.0.0",
    chromium: "140.0.0.0",
    node: "24.15.0",
    v8: "14.0.0",
    os: "Windows_NT x64 10.0.26300",
  });
  assert.match(detail, /^Version: 1\.0\.3b1$/m);
  assert.equal(detail.includes("Commit:"), false);
  assert.equal(detail.includes("Date:"), false);
});

test("git stamp prefers the checkout and falls back to the baked values", () => {
  assert.deepEqual(
    resolveGitStamp(() => null, {
      commit: "abc",
      date: "2026-10-28T04:18:03+08:00",
    }),
    { commit: "abc", date: "2026-10-27T20:18:03Z" },
  );
  assert.deepEqual(
    resolveGitStamp((args) => (args[0] === "rev-parse" ? "deadbeef" : "2026-01-02T03:04:05Z")),
    { commit: "deadbeef", date: "2026-01-02T03:04:05Z" },
  );
});
