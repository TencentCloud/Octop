#!/usr/bin/env node
// Claude Code ``Stop`` hook: ship this session's transcript into octop memory.
//
// Claude-Code-specific in exactly two ways: the payload carries
// ``transcript_path``, and ``Stop`` fires *before* the current turn is flushed —
// so the hook hands the work to a detached worker that polls until an assistant
// record shows up after the last user record. The hook itself returns at once.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { capture, isConfigured, loadConfig, makeLogger, sleep } from "../lib/octop-memory-client.mjs";

const log = makeLogger("stopcap.claude-code");
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
      process.exit(0); // the hook returns at once; the worker waits, then uploads
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

/** The turn landed when an assistant record follows the last user record. */
function turnLanded(path) {
  try {
    let lastUser = -1;
    let lastAssistant = -1;
    const lines = fs.readFileSync(path, "utf8").split("\n");
    lines.forEach((line, index) => {
      if (!line.trim()) return;
      let record;
      try {
        record = JSON.parse(line);
      } catch {
        return;
      }
      if (record.type === "user") lastUser = index;
      else if (record.type === "assistant") lastAssistant = index;
    });
    return lastAssistant > lastUser;
  } catch {
    return true; // unreadable -> do not wait
  }
}

if (IS_WORKER) {
  if (DELAY_MS > 0) await sleep(DELAY_MS);
  const deadline = Date.now() + MAX_WAIT_MS;
  let waited = 0;
  while (Date.now() < deadline && !turnLanded(transcriptPath)) {
    await sleep(POLL_MS);
    waited += POLL_MS;
  }
  if (waited) log(`${event} waited ${waited}ms for the turn to land`);
}

const config = loadConfig();
if (!isConfigured(config)) {
  log("skip: not configured (need OCTOP_MEMORY_MCP_URL / _TOKEN / _AGENT_ID or config.json)");
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
  source: "claude-code",
  sessionId,
  transcriptPath,
  buffer,
  sessionPrefix: "cc:",
});
process.exit(0);
