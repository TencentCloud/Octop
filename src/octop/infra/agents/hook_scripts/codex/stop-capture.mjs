#!/usr/bin/env node
// Codex CLI ``Stop`` hook: ship this session's rollout transcript into octop memory.
//
// Codex-specific: hooks are declared in ``~/.codex/config.toml``
// (``[[hooks.Stop]]`` with ``type = "command"``), the payload carries
// ``transcript_path`` (the ``rollout-*.jsonl`` under ``~/.codex/sessions``) and
// ``session_id``, and — like Claude Code — Stop can fire before the turn is
// flushed, so the hook defers to a detached worker and waits for the file to stop
// growing.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { capture, isConfigured, loadConfig, makeLogger, sleep } from "../lib/octop-memory-client.mjs";

const log = makeLogger("stopcap.codex");
const DELAY_MS = Number(process.env.OCTOP_CAPTURE_DELAY_MS ?? 3000);
const POLL_MS = Number(process.env.OCTOP_CAPTURE_POLL_MS ?? 1000);
const MAX_WAIT_MS = Number(process.env.OCTOP_CAPTURE_MAX_WAIT_MS ?? 20000);
const IS_WORKER = process.argv.includes("--worker");

let raw = "";
if (IS_WORKER) {
  raw = Buffer.from(process.env.OCTOP_HOOK_PAYLOAD_B64 || "", "base64").toString("utf8");
} else {
  try {
    raw = fs.readFileSync(0, "utf8");
  } catch {
    raw = "";
  }
  if (process.env.OCTOP_CAPTURE_SYNC !== "1") {
    try {
      const worker = spawn(process.execPath, [fileURLToPath(import.meta.url), "--worker"], {
        detached: true,
        stdio: "ignore",
        env: { ...process.env, OCTOP_HOOK_PAYLOAD_B64: Buffer.from(raw).toString("base64") },
      });
      worker.unref();
      log(`deferred: 交给后台进程，等本轮落盘（${DELAY_MS}ms 起轮询）`);
      process.exit(0);
    } catch (exc) {
      log(`detach failed, running inline: ${exc}`);
    }
  }
}
let hookInput = {};
try {
  if (raw.trim()) hookInput = JSON.parse(raw);
} catch {
  log("stdin-not-json");
}

const sessionId = hookInput.session_id || "";
const event = hookInput.hook_event_name || "Stop";
const transcriptPath = hookInput.transcript_path || "";
if (!transcriptPath) {
  log(`${event} skip: payload has no transcript_path`);
  process.exit(0);
}

if (IS_WORKER) {
  if (DELAY_MS > 0) await sleep(DELAY_MS);
  const deadline = Date.now() + MAX_WAIT_MS;
  let previousSize = -1;
  let waited = 0;
  while (Date.now() < deadline) {
    let size;
    try {
      size = fs.statSync(transcriptPath).size;
    } catch {
      break;
    }
    if (size === previousSize) break;
    previousSize = size;
    await sleep(POLL_MS);
    waited += POLL_MS;
  }
  if (waited) log(`${event} waited ${waited}ms for the rollout to settle`);
}

const config = loadConfig();
if (!isConfigured(config)) {
  log("skip: not configured");
  process.exit(0);
}
let buffer;
try {
  buffer = fs.readFileSync(transcriptPath);
} catch (exc) {
  log(`${event} read failed: ${exc} (${transcriptPath})`);
  process.exit(0);
}
await capture({
  config,
  log,
  event,
  source: "codex",
  sessionId,
  transcriptPath,
  buffer,
  sessionPrefix: "codex:",
});
process.exit(0);
