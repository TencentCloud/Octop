#!/usr/bin/env node
// Kiro ``Stop`` hook: ship this session's ``messages.jsonl`` into octop memory.
//
// Kiro-specific: the payload has no file path (only ``sess_…``), so the session
// file is located as ``<sessions root>/<workspace>/<session id>/messages.jsonl``.
import fs from "node:fs";
import os from "node:os";
import { capture, isConfigured, loadConfig, makeLogger, readStdinJson, sleep } from "../lib/octop-memory-client.mjs";

const log = makeLogger("stopcap.kiro");
const event = "Stop";
const sessionId = readStdinJson(log).session_id || "";
if (!sessionId) {
  log(`${event} skip: payload has no session_id`);
  process.exit(0);
}

const root = process.env.OCTOP_KIRO_SESSIONS_ROOT || `${os.homedir()}/.kiro/sessions`;
function findSessionFile(id) {
  try {
    for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const candidate = `${root}/${entry.name}/${id}/messages.jsonl`;
      if (fs.existsSync(candidate)) return candidate;
    }
  } catch {
    // no Kiro install / unreadable root
  }
  return "";
}

const transcriptPath = findSessionFile(sessionId);
if (!transcriptPath) {
  log(`${event} skip: no transcript for ${sessionId} under ${root}`);
  process.exit(0);
}

// Kiro's Stop also fires before the file settles: wait until its size stops growing.
const POLL_MS = Number(process.env.OCTOP_CAPTURE_POLL_MS ?? 1000);
const MAX_WAIT_MS = Number(process.env.OCTOP_CAPTURE_MAX_WAIT_MS ?? 20000);
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
if (waited) log(`${event} waited ${waited}ms for the file to settle`);

const config = loadConfig();
if (!isConfigured(config)) {
  log("skip: not configured");
  process.exit(0);
}
const buffer = fs.readFileSync(transcriptPath);
await capture({
  config,
  log,
  event,
  source: "kiro",
  sessionId,
  transcriptPath,
  buffer,
  sessionPrefix: "kiro:",
});
process.exit(0);
