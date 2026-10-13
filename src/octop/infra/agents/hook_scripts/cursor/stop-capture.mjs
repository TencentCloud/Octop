#!/usr/bin/env node
// Cursor ``stop`` hook: ship this session's transcript into octop memory.
//
// Cursor-specific: hooks live in ``~/.cursor/hooks.json`` (``{"version":1,
// "hooks":{"stop":[{"command":…}]}}``) and the payload carries ``transcript_path``
// plus ``conversation_id`` / ``session_id``. That path is
// ``~/.cursor/projects/<workspace>/agent-transcripts/<id>/<id>.jsonl``
// (one JSON object per line: ``{role, message:{content:[{type,text}]}}``).
// ``~/.cursor/chats/**/store.db`` is protobuf and is not read — if a payload has
// no ``transcript_path``, this logs and skips instead of guessing.
import fs from "node:fs";
import { capture, isConfigured, loadConfig, makeLogger, readStdinJson, sleep } from "../lib/octop-memory-client.mjs";

const log = makeLogger("stopcap.cursor");
const hookInput = readStdinJson(log);
const event = hookInput.hook_event_name || "stop";
const sessionId = hookInput.conversation_id || hookInput.session_id || "";
const transcriptPath = hookInput.transcript_path || "";
if (!transcriptPath) {
  log(`${event} skip: payload has no transcript_path (session=${sessionId})`);
  process.exit(0);
}

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
if (waited) log(`${event} waited ${waited}ms for the transcript to settle`);

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
  source: "cursor",
  sessionId,
  transcriptPath,
  buffer,
  sessionPrefix: "cursor:",
});
process.exit(0);
