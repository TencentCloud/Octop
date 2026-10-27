import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { SidecarSupervisor } from "./sidecar";

/**
 * §6.3 refuses an install unless Python exited BY ITSELF with code 0, so `stop`
 * has to distinguish "honoured SIGTERM" from "had to be SIGKILLed".
 */

async function waitForFile(path: string, timeoutMs = 3_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (existsSync(path)) return;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 20));
  }
  throw new Error(`timed out waiting for ${path}`);
}

async function withSupervisor(
  handler: string,
  fn: (supervisor: SidecarSupervisor) => Promise<void>,
): Promise<void> {
  const dir = await mkdtemp(join(tmpdir(), "octop-sidecar-"));
  const marker = join(dir, "ready");
  // The marker file tells us the signal handler is installed before we signal.
  const script = [
    "const fs = require('node:fs');",
    `process.on('SIGTERM', () => { ${handler} });`,
    "fs.writeFileSync(process.argv[1], 'ready');",
    "setInterval(() => {}, 1000);",
  ].join("");
  const supervisor = new SidecarSupervisor({
    executable: process.execPath,
    args: ["-e", script, marker],
    env: process.env,
    cwd: dir,
    port: 1,
  });
  try {
    supervisor.start();
    await waitForFile(marker);
    await fn(supervisor);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("stop() reports a clean exit when the child exits 0 on SIGTERM", async () => {
  await withSupervisor("process.exit(0);", async (supervisor) => {
    const exit = await supervisor.stop(5_000);
    assert.deepEqual(exit, { clean: true, exitCode: 0 });
  });
});

test("stop() reports unclean when the child ignores SIGTERM", async () => {
  await withSupervisor("/* keep running */", async (supervisor) => {
    const exit = await supervisor.stop(300);
    assert.equal(exit.clean, false);
    assert.equal(exit.exitCode, null);
  });
});

test("stop() reports unclean when the child exits non-zero", async () => {
  await withSupervisor("process.exit(3);", async (supervisor) => {
    const exit = await supervisor.stop(5_000);
    assert.deepEqual(exit, { clean: false, exitCode: 3 });
  });
});

test("stop() is a no-op when the sidecar was never started", async () => {
  const supervisor = new SidecarSupervisor({
    executable: process.execPath,
    args: ["-e", "setInterval(() => {}, 1000);"],
    env: process.env,
    cwd: process.cwd(),
    port: 1,
  });
  assert.deepEqual(await supervisor.stop(50), { clean: true, exitCode: null });
});

test("stop() is a no-op after the child already exited", async () => {
  const dir = await mkdtemp(join(tmpdir(), "octop-sidecar-"));
  const marker = join(dir, "ready");
  const supervisor = new SidecarSupervisor({
    executable: process.execPath,
    args: ["-e", "require('node:fs').writeFileSync(process.argv[1], 'ready');", marker],
    env: process.env,
    cwd: dir,
    port: 1,
  });
  try {
    supervisor.start();
    await waitForFile(marker);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    assert.deepEqual(await supervisor.stop(50), { clean: true, exitCode: null });
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
