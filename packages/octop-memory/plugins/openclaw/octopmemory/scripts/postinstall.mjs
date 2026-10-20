#!/usr/bin/env node
/**
 * postinstall.mjs — after `openclaw plugins install @octop-memory/openclaw`,
 * automatically write plugins.slots.memory = octopmemory into openclaw.json.
 *
 * Flow:
 *   1. Check whether `octopmemory-bridge --probe` succeeds.
 *      ├── success → call `octop-memory openclaw setup` to write openclaw.json.
 *      └── failure → print friendly guidance to install the Python package first.
 *
 * Design principles:
 *   - Any error should only print a warning and must not fail npm install.
 *   - Add no npm dependencies; use only built-in Node.js modules.
 *   - Stay idempotent so repeated installs do not damage existing config.
 */

import { execFileSync, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// Color output, enabled only for TTY.
// ---------------------------------------------------------------------------
const isTTY = process.stdout.isTTY;
const C = {
  green: isTTY ? "\x1b[32m" : "",
  yellow: isTTY ? "\x1b[33m" : "",
  red: isTTY ? "\x1b[31m" : "",
  cyan: isTTY ? "\x1b[36m" : "",
  reset: isTTY ? "\x1b[0m" : "",
};

const log = {
  step: (msg) => console.log(`${C.cyan}[octopmemory]${C.reset} ${msg}`),
  ok: (msg) => console.log(`${C.green}[octopmemory] ✓${C.reset} ${msg}`),
  warn: (msg) => console.warn(`${C.yellow}[octopmemory] !${C.reset} ${msg}`),
  fail: (msg) => console.error(`${C.red}[octopmemory] ✗${C.reset} ${msg}`),
};

// ---------------------------------------------------------------------------
// Skip conditions: CI or explicit opt-out.
// ---------------------------------------------------------------------------
if (process.env.CI || process.env.OCTOPMEMORY_SKIP_POSTINSTALL === "1") {
  log.step("跳过 postinstall（CI 或 OCTOPMEMORY_SKIP_POSTINSTALL=1）");
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Find an executable in PATH, returning its full path or null.
 * Also check common uv / pipx tool installation locations.
 */
function findExecutable(name) {
  // Check PATH first with which / where.
  const whichCmd = process.platform === "win32" ? "where" : "which";
  const r = spawnSync(whichCmd, [name], { encoding: "utf8" });
  if (r.status === 0 && r.stdout.trim()) {
    return r.stdout.trim().split("\n")[0].trim();
  }

  // Also check common uv tool / pipx install locations.
  const extraDirs = [
    join(homedir(), ".local", "bin"),
    join(homedir(), ".cargo", "bin"),      // uv itself is sometimes installed here.
    "/usr/local/bin",
    "/opt/homebrew/bin",
  ];
  for (const dir of extraDirs) {
    const candidate = join(dir, name);
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

/**
 * Check whether octopmemory-bridge is available and FTS5 works.
 * Return { ok: boolean, path: string|null, reason: string }.
 */
function probeBridge() {
  const bridgePath = findExecutable("octopmemory-bridge");
  if (!bridgePath) {
    return { ok: false, path: null, reason: "octopmemory-bridge 不在 PATH 中" };
  }

  const r = spawnSync(bridgePath, ["--probe"], { encoding: "utf8", timeout: 8000 });
  if (r.status !== 0 || r.error) {
    return {
      ok: false,
      path: bridgePath,
      reason: `octopmemory-bridge --probe 失败（exit ${r.status}）: ${r.stderr?.trim() || r.error?.message || ""}`,
    };
  }

  // --probe outputs JSON; check the fts5 field.
  try {
    const probe = JSON.parse(r.stdout.trim());
    if (probe.fts5 === false) {
      return {
        ok: false,
        path: bridgePath,
        reason: `Python 的 SQLite 没有 FTS5 支持（${probe.sqlite_version ?? ""}）。请用 uv tool install 安装以获得带 FTS5 的 Python。`,
      };
    }
  } catch {
    // Non-JSON --probe output still passes when the process exits with 0.
  }

  return { ok: true, path: bridgePath, reason: "" };
}

/**
 * Find the octop-memory CLI command.
 */
function findOctopCli() {
  return findExecutable("octop-memory");
}

/**
 * Run `octop-memory openclaw setup` to write openclaw.json.
 * Return { ok: boolean, output: string }.
 */
function runSetup(cliPath, bridgePath) {
  const args = [
    "openclaw", "setup",
    "--bridge-python", "python3",  // Default value; users can override it later with setup.
  ];

  // If the bridge is an absolute path from uv tool, write command too so
  // openclaw.json points directly at the executable and does not depend on
  // PATH visibility inside the OpenClaw process.
  if (bridgePath && bridgePath !== "octopmemory-bridge") {
    args.push("--bridge-command", bridgePath);
  }

  const r = spawnSync(cliPath, args, {
    encoding: "utf8",
    timeout: 15000,
    env: { ...process.env },
  });

  const output = [r.stdout, r.stderr].filter(Boolean).join("\n").trim();
  return { ok: r.status === 0 && !r.error, output };
}

// ---------------------------------------------------------------------------
// Main flow
// ---------------------------------------------------------------------------

async function main() {
  log.step("检测 Python bridge（octopmemory-bridge）…");

  const probe = probeBridge();

  if (!probe.ok) {
    // Bridge is unavailable: print friendly guidance without failing.
    log.warn("未检测到可用的 octopmemory-bridge，跳过自动配置。");
    log.warn(`原因：${probe.reason}`);
    console.log("");
    console.log("  请先安装 Python bridge，然后手动运行 setup：");
    console.log("");
    console.log(`  ${C.cyan}# 推荐（uv 自带 FTS5 Python）${C.reset}`);
    console.log(`  ${C.green}uv tool install 'octop-memory[cli]'${C.reset}`);
    console.log("");
    console.log(`  ${C.cyan}# 或者用 pip${C.reset}`);
    console.log(`  ${C.green}pip install 'octop-memory[cli]'${C.reset}`);
    console.log("");
    console.log(`  ${C.cyan}# 安装后运行 setup${C.reset}`);
    console.log(`  ${C.green}octop-memory openclaw setup${C.reset}`);
    console.log("");
    console.log("  安装完成后重启 OpenClaw，/octopmemory 命令即可出现。");
    console.log("");
    return;
  }

  log.ok(`找到 bridge：${probe.path}`);

  // Find the octop-memory CLI.
  const cliPath = findOctopCli();
  if (!cliPath) {
    log.warn("找到了 octopmemory-bridge 但找不到 octop-memory CLI，跳过自动 setup。");
    log.warn("请手动运行：octop-memory openclaw setup");
    return;
  }

  log.step("运行 octop-memory openclaw setup…");
  const setup = runSetup(cliPath, probe.path);

  if (setup.ok) {
    log.ok("openclaw.json 已自动配置完成！");
    if (setup.output) {
      // Indent output for readability.
      console.log(setup.output.split("\n").map((l) => `  ${l}`).join("\n"));
    }
    console.log("");
    console.log(`  ${C.green}重启 OpenClaw 后，在对话框输入 / 即可看到 /octopmemory${C.reset}`);
    console.log("");
  } else {
    log.warn("自动 setup 失败，请手动运行：octop-memory openclaw setup");
    if (setup.output) {
      console.log(setup.output.split("\n").map((l) => `  ${l}`).join("\n"));
    }
  }
}

main().catch((err) => {
  // postinstall must never fail npm install.
  log.warn(`postinstall 遇到意外错误（已忽略）：${err?.message ?? err}`);
  process.exit(0);
});
