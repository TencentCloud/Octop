// Shared transport for every octop-memory host hook.
//
// Host-independent on purpose: this module knows how to talk to the memory MCP
// (config, auth, incremental offsets, logging, gzip, DSH's zstd container) and
// nothing about *which* terminal called it. Each host gets its own entry script
// under ``<host>/`` that decides what to read and which ``source`` /
// ``session_id`` prefix to use — so changing one host never touches another.
//
// Config precedence: environment variable -> ``config.json`` next to the entry
// script (the /mcp/memory/setup installer writes that file, so a hooked-up
// terminal needs no secret in its hook command line).
import fs from "node:fs";
import os from "node:os";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ENTRY_DIR = path.dirname(fileURLToPath(import.meta.url));
const HOOK_DIR = path.dirname(ENTRY_DIR); // .../hook_scripts (or the host dir)

// Where this hook may write. Claude Code runs hooks unsandboxed, so the hook
// directory next to the scripts works. DSH runs the same command hooks inside a
// workspace-write sandbox whose writable roots are the session workspace, /tmp
// and the process temp dir: a $HOME hook directory stays readable there but every
// log/state write is denied — silently, because both are best-effort. Probe once
// and fall back to a private temp directory so the incremental offset and the
// diagnostic log survive in both worlds.
function resolveScratchDir() {
  for (const dir of [HOOK_DIR, `${os.tmpdir()}/octop-hooks`]) {
    const probe = `${dir}/.octop-write-probe`;
    try {
      fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
      fs.writeFileSync(probe, "");
      fs.unlinkSync(probe);
      return dir;
    } catch {
      // not writable here -> try the next candidate
    }
  }
  return HOOK_DIR;
}

export const paths = (() => {
  const scratchDir = resolveScratchDir();
  if (scratchDir !== HOOK_DIR) {
    process.stderr.write(
      `octop-memory: ${HOOK_DIR} 不可写，日志与增量状态改写到 ${scratchDir}\n`,
    );
  }
  return {
    hookDir: HOOK_DIR,
    configPath: `${HOOK_DIR}/config.json`,
    scratchDir,
    logPath: `${scratchDir}/octop-hook.log`,
    statePath: `${scratchDir}/octop-transcript-state.json`,
  };
})();

export function loadConfig() {
  let fromFile = {};
  try {
    fromFile = JSON.parse(fs.readFileSync(paths.configPath, "utf8"));
  } catch {
    // no config file (env-only setups keep working)
  }
  return {
    endpoint: process.env.OCTOP_MEMORY_MCP_URL || fromFile.url || "",
    token: process.env.OCTOP_MEMORY_MCP_TOKEN || fromFile.token || "",
    agentId: process.env.OCTOP_AGENT_ID || fromFile.agentId || "",
    userId: process.env.OCTOP_USER_ID || fromFile.userId || "",
    // Configurable header name; ``Authorization`` (the default) takes a bearer.
    tokenHeader: process.env.OCTOP_TOKEN_HEADER || fromFile.tokenHeader || "Authorization",
  };
}

function baseHeaders(config) {
  const headers = {
    "X-Octop-Agent-Id": config.agentId,
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
  };
  if (config.userId) headers["X-Octop-User-Id"] = config.userId;
  return headers;
}

export function authHeaders(config) {
  // One configurable header carries the token: ``Authorization`` (the default)
  // takes ``Bearer <token>``, any other header name is written verbatim.
  const headers = baseHeaders(config);
  const header = config.tokenHeader || "Authorization";
  headers[header] = header.toLowerCase() === "authorization" ? `Bearer ${config.token}` : config.token;
  return headers;
}

/**
 * Whether these hooks have somewhere to send to: an endpoint, an agent, and a token.
 */
export function isConfigured(config) {
  return !!config.endpoint && !!config.agentId && !!config.token;
}

/** One logger per host: ``tag`` is what shows up in the shared log file. */
export function makeLogger(tag) {
  return (line) => {
    try {
      fs.appendFileSync(paths.logPath, `[${new Date().toISOString()}] ${tag}: ${line}\n`, {
        mode: 0o600,
      });
    } catch {
      // logging must never break the hook
    }
  };
}

export function loadState() {
  try {
    return JSON.parse(fs.readFileSync(paths.statePath, "utf8"));
  } catch {
    return {};
  }
}

export function saveState(state) {
  try {
    fs.writeFileSync(paths.statePath, JSON.stringify(state), { mode: 0o600 });
  } catch {
    // a lost offset only costs one redundant (idempotent) upload
  }
}

/** Read the hook payload from stdin (the host hands it over as JSON). */
export function readStdinJson(log) {
  try {
    const raw = fs.readFileSync(0, "utf8");
    return raw.trim() ? JSON.parse(raw) : {};
  } catch {
    log("stdin-not-json");
    return {};
  }
}

// Decode DSH's session container: it is a concatenation of independently
// decodable Zstandard frames (one header frame, then one frame per durable
// batch). Node's zstd API stops after the first frame, so a whole-file
// ``zstdDecompressSync`` silently returns only the session header. Walk the
// frames structurally and decode each complete one; a torn final frame is left
// for the next Stop to pick up.
export function decompressZstdContainer(buffer) {
  const ZSTD_MAGIC = 0xfd2fb528;
  const parts = [];
  let offset = 0;
  while (offset < buffer.length) {
    const start = offset;
    if (buffer.length - offset < 4) break;
    if (buffer.readUInt32LE(offset) !== ZSTD_MAGIC) {
      throw new Error(`invalid Zstandard frame magic at byte ${offset}`);
    }
    offset += 4;
    if (offset === buffer.length) break;
    const descriptor = buffer.readUInt8(offset);
    offset += 1;
    if ((descriptor & 0x18) !== 0) {
      throw new Error(`reserved Zstandard frame-header bit at byte ${offset - 1}`);
    }
    const contentSizeFlag = descriptor >>> 6;
    const singleSegment = (descriptor & 0x20) !== 0;
    const checksum = (descriptor & 0x04) !== 0;
    const dictionaryFlag = descriptor & 0x03;
    const dictionaryBytes = dictionaryFlag === 3 ? 4 : dictionaryFlag;
    const contentSizeBytes = contentSizeFlag === 0 ? (singleSegment ? 1 : 0) : 1 << contentSizeFlag;
    const remainingHeaderBytes = (singleSegment ? 0 : 1) + dictionaryBytes + contentSizeBytes;
    if (buffer.length - offset < remainingHeaderBytes) break;
    offset += remainingHeaderBytes;

    let torn = false;
    for (;;) {
      if (buffer.length - offset < 3) {
        torn = true;
        break;
      }
      const blockHeader = buffer.readUIntLE(offset, 3);
      offset += 3;
      const lastBlock = (blockHeader & 1) !== 0;
      const blockType = (blockHeader >>> 1) & 0x03;
      const blockSize = blockHeader >>> 3;
      if (blockType === 0x03) throw new Error(`reserved Zstandard block type at byte ${offset - 3}`);
      const payloadBytes = blockType === 0x01 ? 1 : blockSize;
      if (buffer.length - offset < payloadBytes) {
        torn = true;
        break;
      }
      offset += payloadBytes;
      if (lastBlock) break;
    }
    if (torn) break;
    if (checksum) {
      if (buffer.length - offset < 4) break;
      offset += 4;
    }
    parts.push(zlib.zstdDecompressSync(buffer.subarray(start, offset)));
  }
  return Buffer.concat(parts);
}

/** Call one memory MCP tool; returns ``{ok, status, detail, raw}`` (never throws). */
export async function callTool(config, name, args) {
  return rpc(config, "tools/call", { name, arguments: args });
}

/** One raw JSON-RPC call; returns ``{ok, status, detail, error, raw}`` (never throws). */
export async function rpc(config, method, params) {
  const response = await fetch(config.endpoint, {
    method: "POST",
    headers: authHeaders(config),
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const text = await response.text();
  let payload = text;
  for (const line of text.split("\n")) {
    if (line.startsWith("data: ")) {
      payload = line.slice(6);
      break;
    }
  }
  let parsed = {};
  try {
    parsed = JSON.parse(payload.slice(payload.indexOf("{"), payload.lastIndexOf("}") + 1));
  } catch {
    // keep the raw body for diagnostics
  }
  return {
    ok: response.ok,
    status: response.status,
    detail: parsed?.result?.structuredContent ?? parsed?.result ?? {},
    error: parsed?.error?.message ?? "",
    raw: text,
  };
}

/**
 * Whether this endpoint's ``memory_capture`` takes the assistant side as its own
 * field (``assistant``) instead of expecting one merged ``content``.
 */
export async function supportsAssistant(config) {
  const result = await rpc(config, "tools/list", {});
  const tool = (result.detail?.tools ?? []).find((entry) => entry?.name === "memory_capture");
  return Object.prototype.hasOwnProperty.call(tool?.inputSchema?.properties ?? {}, "assistant");
}

/**
 * Ship already-grouped conversation turns with the roles in their own fields:
 * ``content`` = the user side, ``assistant`` = the assistant side.
 *
 * Each accepted turn advances the per-``session_id`` offset, so a failure or a
 * cap resumes at the next turn instead of re-sending the whole session.
 */
export async function captureTurns(ctx) {
  const { config, log, event, source, sessionId, transcriptPath, turns, sessionPrefix } = ctx;
  const state = loadState();
  let sent = 0;
  let status = 0;
  let offset = ctx.startOffset ?? 0;
  for (const turn of turns) {
    const args = { content: turn.user.join("\n\n"), source };
    if (sessionId) args.session_id = `${sessionPrefix}${sessionId}`;
    if (turn.assistant.length) args.assistant = turn.assistant.join("\n\n");
    const result = await callTool(config, "memory_capture", args);
    status = result.status;
    if (!result.ok) {
      log(
        `${event} session=${sessionId} turn ${sent + 1} http=${status} ` +
          `err=${result.detail?.error ?? result.error ?? ""} -> offset kept at ${offset}`,
      );
      break;
    }
    sent += 1;
    offset = turn.endOffset;
    if (sessionId) {
      state[sessionId] = { path: transcriptPath, offset };
      saveState(state);
    }
  }
  return { sent, status, offset };
}

/**
 * Ship the *new* bytes of a session file to ``memory_capture``.
 *
 * The offset is per ``session_id`` and only advances after a 2xx; a failed
 * upload is retried in full next time, and the server dedupes on record keys, so
 * re-sending is free.
 */
export async function capture(ctx) {
  const { config, log, event, source, sessionId, transcriptPath, buffer, sessionPrefix } = ctx;
  const state = loadState();
  const previous = sessionId ? state[sessionId] : undefined;

  let start = 0;
  if (previous && previous.path === transcriptPath && previous.offset <= buffer.length) {
    start = previous.offset;
    // Only a boundary that still follows a newline is safe to resume from; a
    // rewritten/compacted file falls back to a full (idempotent) re-send.
    if (start > 0 && start < buffer.length && buffer[start - 1] !== 0x0a) start = 0;
  }
  if (start >= buffer.length) {
    log(`${event} session=${sessionId} no new bytes (offset=${start}) -> skip`);
    return { skipped: true };
  }

  const delta = buffer.subarray(start);
  const whole = start === 0;
  let blob;
  try {
    blob = zlib.gzipSync(delta).toString("base64");
  } catch (exc) {
    log(`${event} gzip failed: ${exc}`);
    return { failed: true };
  }

  const args = { content: blob, source };
  if (sessionId) args.session_id = `${sessionPrefix}${sessionId}`;
  // Opt-in only: the server default is "none" (tool traffic is most of a
  // transcript's bytes and distorts both extraction and raw-layer recall), so set
  // this to "all"/"calls" only for a terminal that needs the full record.
  if (process.env.OCTOP_TOOL_EVENTS) args.tool_events = process.env.OCTOP_TOOL_EVENTS;

  try {
    const result = await callTool(config, "memory_capture", args);
    const detail = result.detail ?? {};
    log(
      `${event} session=${sessionId} source=${source} http=${result.status} ` +
        `mode=${whole ? "full" : "delta"} from=${start} bytes=${delta.length} gz=${blob.length} ` +
        `parsed=${detail.parsed} imported=${detail.imported} skipped=${detail.skipped_existing} ` +
        `extract=${detail.extract_scheduled} err=${detail.error ?? result.error ?? ""}`,
    );
    if (result.ok && sessionId) {
      state[sessionId] = { path: transcriptPath, offset: buffer.length };
      saveState(state);
    }
    return { status: result.status, detail };
  } catch (exc) {
    log(`${event} upload failed: ${exc}`);
    return { failed: true };
  }
}

/** Latest mtime order helper for hosts that discover their session file. */
export function newestFile(dir, pattern) {
  try {
    return fs
      .readdirSync(dir)
      .filter((name) => pattern.test(name))
      .map((name) => ({ name, path: `${dir}/${name}`, mtime: fs.statSync(`${dir}/${name}`).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime)[0]?.path ?? "";
  } catch {
    return "";
  }
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
