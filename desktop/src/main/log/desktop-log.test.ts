import assert from "node:assert/strict";
import { mkdtemp, mkdir, readdir, readFile, rm, stat, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { gunzipSync } from "node:zlib";

import { desktopLogPath, installDesktopLog, openDesktopLog } from "./desktop-log";

test("desktopLogPath sits in logs/desktop beside the Python log", () => {
  assert.equal(
    desktopLogPath(join("home", ".octop")),
    join("home", ".octop", "logs", "desktop", "desktop.log"),
  );
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
    const log = openDesktopLog(path, { maxBytes: 80, compressRotated: false });
    log.info("first line that should roll away");
    log.info("second line that should roll away");
    log.info("kept");
    const current = await readFile(path, "utf8");
    const rotated = (await readdir(dir)).filter((name) => name !== "desktop.log");
    assert.equal(rotated.length, 1);
    const archived = rotated[0];
    assert.ok(archived);
    assert.match(archived, /^desktop\.\d{4}-\d{2}-\d{2}\.log$/);
    const previous = await readFile(join(dir, archived), "utf8");
    assert.match(current, /INFO kept\n/);
    assert.doesNotMatch(current, /first line/);
    assert.match(previous, /first line/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("openDesktopLog rolls a previous day's file under that day's name", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const path = join(dir, "desktop.log");
    const yesterday = previousLocalNoon();
    await writeFile(path, "yesterday line\n");
    await utimes(path, yesterday, yesterday);
    const log = openDesktopLog(path, { maxBytes: 0, compressRotated: false });
    log.info("today");
    const archived = join(dir, `desktop.${localDateStamp(yesterday)}.log`);
    assert.match(await readFile(archived, "utf8"), /yesterday line/);
    const current = await readFile(path, "utf8");
    assert.match(current, /INFO today\n/);
    assert.doesNotMatch(current, /yesterday line/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("openDesktopLog uses a numeric suffix when the day's file already exists", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const path = join(dir, "desktop.log");
    const today = localDateStamp(new Date());
    await writeFile(join(dir, `desktop.${today}.log`), "already\n");
    const log = openDesktopLog(path, { maxBytes: 20, compressRotated: false });
    log.info("one");
    log.info("two");
    assert.equal(await readFile(join(dir, `desktop.${today}.log`), "utf8"), "already\n");
    const extra = await readFile(join(dir, `desktop.${today}.log.001`), "utf8");
    assert.match(extra, /INFO one\n/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("openDesktopLog gzips the previous same-day roll and leaves the newest plain", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const path = join(dir, "desktop.log");
    const log = openDesktopLog(path, { maxBytes: 20 });
    log.info("aaaa");
    log.info("bbbb");
    log.info("cccc");
    const names = await readdir(dir);
    const today = localDateStamp(new Date());
    assert.equal(names.includes(`desktop.${today}.log.gz`), true);
    assert.equal(names.includes(`desktop.${today}.log.001`), true);
    assert.match(gunzipSync(await readFile(join(dir, `desktop.${today}.log.gz`))).toString("utf8"), /INFO aaaa\n/);
    assert.match(await readFile(join(dir, `desktop.${today}.log.001`), "utf8"), /INFO bbbb\n/);
    assert.match(await readFile(path, "utf8"), /INFO cccc\n/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("openDesktopLog gzips older rotated files and leaves the newest plain", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const older = join(dir, "desktop.2026-01-01.log");
    const newer = join(dir, "desktop.2026-01-02.log");
    await writeFile(older, "older\n");
    await writeFile(newer, "newer\n");
    const past = new Date(Date.now() - 86_400_000);
    await utimes(older, past, past);
    openDesktopLog(join(dir, "desktop.log"));
    assert.equal(await exists(older), false);
    assert.equal(gunzipSync(await readFile(`${older}.gz`)).toString("utf8"), "older\n");
    assert.equal(await readFile(newer, "utf8"), "newer\n");
    assert.equal(await exists(`${newer}.gz`), false);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("openDesktopLog deletes rotated files older than the retention window", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  try {
    const old = join(dir, "desktop.2020-01-01.log");
    const recent = join(dir, "desktop.2026-07-16.log.gz");
    await writeFile(old, "old\n");
    await writeFile(recent, "new\n");
    const ancient = new Date(Date.now() - 100 * 86_400_000);
    const recentTime = new Date(Date.now() - 86_400_000);
    await utimes(old, ancient, ancient);
    await utimes(recent, recentTime, recentTime);
    openDesktopLog(join(dir, "desktop.log"), { retentionDays: 14 });
    assert.equal(await exists(old), false);
    assert.equal(await exists(recent), true);
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

test("installDesktopLog moves the legacy single file into logs/desktop", async () => {
  const home = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  await withEnv({ OCTOP_LOG_COMPRESS: "0", OCTOP_LOG_RETENTION_DAYS: "14" }, async () => {
    try {
      const logs = join(home, "logs");
      await mkdir(logs);
      await writeFile(join(logs, "desktop.log"), "active\n");
      const backup = join(logs, "desktop.log.1");
      const when = previousLocalNoon();
      await writeFile(backup, "backup\n");
      await utimes(backup, when, when);
      const log = installDesktopLog(home);
      assert.equal(log.path, desktopLogPath(home));
      assert.equal(await exists(join(logs, "desktop.log")), false);
      assert.equal(await exists(backup), false);
      assert.equal(await readFile(log.path, "utf8"), "active\n");
      assert.equal(await readFile(join(logs, "desktop", `desktop.${localDateStamp(when)}.log`), "utf8"), "backup\n");
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  });
});

test("installDesktopLog honors OCTOP_LOG_MAX_BYTES", async () => {
  const home = await mkdtemp(join(tmpdir(), "octop-desktop-log-"));
  await withEnv(
    { OCTOP_LOG_MAX_BYTES: "80", OCTOP_LOG_COMPRESS: "0", OCTOP_LOG_RETENTION_DAYS: "14" },
    async () => {
      try {
        const log = installDesktopLog(home);
        log.info("first line that should roll away");
        log.info("second line that should roll away");
        log.info("kept");
        const names = await readdir(join(home, "logs", "desktop"));
        assert.ok(names.some((name) => /^desktop\.\d{4}-\d{2}-\d{2}\.log$/.test(name)));
      } finally {
        await rm(home, { recursive: true, force: true });
      }
    },
  );
});

function previousLocalNoon(): Date {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  date.setHours(12, 0, 0, 0);
  return date;
}

function localDateStamp(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function withEnv(values: Record<string, string | undefined>, run: () => Promise<void>): Promise<void> {
  const saved = new Map<string, string | undefined>();
  for (const [key, value] of Object.entries(values)) {
    saved.set(key, process.env[key]);
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  try {
    await run();
  } finally {
    for (const [key, value] of saved) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}
