#!/usr/bin/env node
// DSH ``Stop`` hook (through the hooks bridge): ship this session's
// ``session*.jsonl.zstd`` into octop memory.
//
// Two shipping modes, chosen by probing the endpoint (force one with
// ``OCTOP_CAPTURE_MODE=text|transcript``):
//
//   text        ``memory_capture`` takes ``assistant`` -> one call per turn with
//               the roles in their own fields, so the assistant's answer is not
//               stored as a user message.
//   transcript  no ``assistant`` field -> gzip the raw JSONL delta and let the
//               server parse typed events (its DSH transcript path).
//
// DSH-specific: the payload has only ``session_id``, the file is versioned
// (``session.jsonl.zstd`` -> ``session.v3.jsonl.zstd`` -> …) so the newest one
// inside the session directory is used, and it is zstd-compressed — decoded here
// so the server needs no zstd dependency.
import fs from "node:fs";
import os from "node:os";
import {
  capture,
  captureTurns,
  decompressZstdContainer,
  isConfigured,
  loadState,
  makeLogger,
  newestFile,
  readStdinJson,
  saveState,
  sleep,
  supportsAssistant,
} from "../lib/octop-memory-client.mjs";
import { resolveConfig } from "./memory-target.mjs";

const log = makeLogger("stopcap.dsh");
const event = "Stop";
const sessionId = readStdinJson(log).session_id || "";
if (!sessionId) {
  log(`${event} skip: payload has no session_id`);
  process.exit(0);
}

const root = process.env.OCTOP_DSH_SESSIONS_ROOT || `${os.homedir()}/.dsh/sessions`;
function findSessionFile(id) {
  try {
    for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const found = newestFile(`${root}/${entry.name}/${id}`, /^session.*\.jsonl\.zstd$/);
      if (found) return found;
    }
  } catch {
    // no DSH install / unreadable root
  }
  return "";
}

const transcriptPath = findSessionFile(sessionId);
if (!transcriptPath) {
  log(`${event} skip: no transcript for ${sessionId} under ${root}`);
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
if (waited) log(`${event} waited ${waited}ms for the file to settle`);

const config = resolveConfig();
if (!isConfigured(config)) {
  log("skip: not configured");
  process.exit(0);
}
let buffer;
try {
  buffer = decompressZstdContainer(fs.readFileSync(transcriptPath));
} catch (exc) {
  log(`${event} zstd decompress failed: ${exc} (${transcriptPath})`);
  process.exit(0);
}

// --- transcript mode: the server parses the records into typed events ---
const forced = (process.env.OCTOP_CAPTURE_MODE || "auto").trim().toLowerCase();
const asTurns =
  forced === "text" ? true : forced === "transcript" ? false : await supportsAssistant(config);
if (!asTurns) {
  await capture({
    config,
    log,
    event,
    source: "dsh",
    sessionId,
    transcriptPath,
    buffer,
    sessionPrefix: "dsh:",
  });
  process.exit(0);
}

// --- text mode: one call per turn, roles in their own fields ---

function textBlocks(content) {
  if (!Array.isArray(content)) return "";
  return content
    .filter((block) => block && block.type === "text" && typeof block.text === "string")
    .map((block) => block.text.trim())
    .filter(Boolean)
    .join("\n");
}

/** Bytes of ``buffer`` that end on a complete JSONL record; a torn tail waits for the next Stop. */
function completeRecordsEnd() {
  const lastNewline = buffer.lastIndexOf(0x0a);
  if (lastNewline + 1 >= buffer.length) return lastNewline + 1;
  const tail = buffer.subarray(lastNewline + 1).toString("utf8").trim();
  if (!tail) return buffer.length;
  try {
    JSON.parse(tail);
    return buffer.length;
  } catch {
    return lastNewline + 1;
  }
}

/**
 * Group the delta into turns with each turn's end offset, so the offset advances
 * one shipped turn at a time. A ``user/message`` starts a turn only when its
 * source kind is ``user`` — plugin snapshots, system reminders and hook
 * injections share that record type; ``assistant/message`` keeps text blocks only.
 */
function turnBatches(start, end) {
  const batches = [];
  const closeTurn = (offset) => {
    if (batches.length) batches[batches.length - 1].endOffset = offset;
  };
  let cursor = start;
  while (cursor < end) {
    const newline = buffer.indexOf(0x0a, cursor);
    const lineEnd = newline === -1 || newline >= end ? end : newline + 1;
    const line = buffer
      .subarray(cursor, lineEnd - (lineEnd === newline + 1 ? 1 : 0))
      .toString("utf8");
    const lineStart = cursor;
    cursor = lineEnd;
    if (!line.trim()) continue;
    let record;
    try {
      record = JSON.parse(line);
    } catch {
      continue; // torn or non-JSON line
    }
    if (record?.type === "user/message") {
      const kind = String(record?.data?.source?.kind || "");
      if (kind && kind !== "user") continue;
      closeTurn(lineStart);
      const text = textBlocks(record?.data?.content);
      batches.push({ user: text ? [text] : [], assistant: [], endOffset: end });
    } else if (record?.type === "assistant/message") {
      const text = textBlocks(record?.data?.message?.content);
      if (!text) continue;
      if (!batches.length) batches.push({ user: [], assistant: [], endOffset: end });
      batches[batches.length - 1].assistant.push(text);
    }
  }
  closeTurn(end);
  return batches.filter((batch) => batch.user.length || batch.assistant.length);
}

const state = loadState();
const previous = state[sessionId];
let start = 0;
if (previous && previous.path === transcriptPath && previous.offset <= buffer.length) {
  start = previous.offset;
  // Only a boundary that still follows a newline is safe to resume from; a
  // rewritten/compacted file falls back to a full re-send.
  if (start > 0 && start < buffer.length && buffer[start - 1] !== 0x0a) start = 0;
}
const end = completeRecordsEnd();
if (end <= start) {
  log(`${event} session=${sessionId} no new records (offset=${start}/${end}) -> skip`);
  process.exit(0);
}
let turns = turnBatches(start, end);
const maxTurns = Number(process.env.OCTOP_CAPTURE_MAX_TURNS ?? 25);
if (turns.length > maxTurns) turns = turns.slice(0, maxTurns);

if (!turns.length) {
  // Tool traffic only: consume it so the next Stop starts after it.
  state[sessionId] = { path: transcriptPath, offset: end };
  saveState(state);
  log(`${event} session=${sessionId} no user/assistant text in ${end - start} bytes -> offset advanced`);
  process.exit(0);
}

const result = await captureTurns({
  config,
  log,
  event,
  source: "dsh",
  sessionId,
  transcriptPath,
  turns,
  sessionPrefix: "dsh:",
  startOffset: start,
});
log(
  `${event} session=${sessionId} source=dsh http=${result.status} mode=text ` +
    `from=${start} bytes=${end - start} turns=${turns.length} sent=${result.sent} offset=${result.offset}`,
);
process.exit(0);
