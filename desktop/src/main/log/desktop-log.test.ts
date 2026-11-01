import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { desktopLogPath, openDesktopLog } from "./desktop-log";

test("desktopLogPath sits beside the Python log", () => {
  assert.equal(desktopLogPath(join("home", ".octop")), join("home", ".octop", "logs", "desktop.log"));
});

test("openDesktopLog appends leveled lines and creates the logs directory", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const path = desktopLogPath(dir);
    const log = openDesktopLog(path);
    log.info("booted");
    log.warn("keychain missing");
    log.error("sidecar down\ntraceback");
    const text = await readFile(path, "utf8");
    assert.match(text, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z INFO booted\n/);
    assert.match(text, /WARN keychain missing\n/);
    assert.match(text, /ERROR sidecar down\n/);
    assert.match(text, /ERROR traceback\n/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("openDesktopLog rolls the file once it passes the size cap", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const path = join(dir, "desktop.log");
    const log = openDesktopLog(path, 80);
    log.info("first line that should roll away");
    log.info("second line that should roll away");
    log.info("kept");
    const current = await readFile(path, "utf8");
    const previous = await readFile(`${path}.1`, "utf8");
    assert.match(current, /INFO kept\n/);
    assert.doesNotMatch(current, /first line/);
    assert.match(previous, /first line/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("openDesktopLog ignores a path it cannot create", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const blocker = join(dir, "not-a-directory");
    await writeFile(blocker, "x");
    const log = openDesktopLog(join(blocker, "logs", "desktop.log"));
    assert.doesNotThrow(() => log.error("still running"));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
