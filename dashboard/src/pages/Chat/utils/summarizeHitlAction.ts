/**
 * Turn a HITL tool-call into a short explanation plus labelled rows.
 * Approval cards should never dump raw JSON as the primary view.
 */

export interface HitlArgRow {
  label: string;
  value: string;
  mono?: boolean;
}

export interface HitlActionView {
  toolLabel: string;
  summary: string;
  rows: HitlArgRow[];
}

export type HitlTranslate = (
  key: string,
  options?: string | Record<string, unknown>,
) => string;

const ALWAYS_HIDDEN = new Set(["session_id", "profile"]);
const TRUNCATE_KEYS = new Set([
  "content",
  "body",
  "html",
  "text",
  "old_string",
  "new_string",
  "code",
  "script",
]);
const BROWSER_TOOLS = new Set(["browser_use", "browser_control"]);
const SHELL_TOOLS = new Set(["execute", "bash", "run_terminal_cmd"]);
const MONO_KEYS = new Set([
  "command",
  "cmd",
  "path",
  "file",
  "file_path",
  "url",
  "code",
  "script",
  "selector",
  "pattern",
]);
const MAX_TRUNCATED = 280;
const MAX_HARD = 2000;

const MACHINE_HITL_DESC = /tool execution requires approval/i;
const TOOL_ARGS_DUMP = /\bTool:\s+\S[\s\S]*\bArgs:\s*[{'"]/;

/** True when harness/langgraph stuffed a raw English args dump into ``description``. */
export function isMachineHitlDescription(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  return MACHINE_HITL_DESC.test(trimmed) || TOOL_ARGS_DUMP.test(trimmed);
}

function resolve(
  t: HitlTranslate,
  key: string,
  fallback: string,
  vars?: Record<string, unknown>,
): string {
  const result = vars
    ? t(key, { defaultValue: fallback, ...vars })
    : t(key, fallback);
  if (!result || result === key) return fallback;
  return result;
}

export function humanizeArgKey(key: string): string {
  const cleaned = key.replace(/[_-]+/g, " ").trim();
  if (!cleaned) return key;
  return cleaned[0].toUpperCase() + cleaned.slice(1);
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "";
}

function shouldHide(key: string, value: unknown): boolean {
  if (ALWAYS_HIDDEN.has(key) || isEmpty(value)) return true;
  return false;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1))}…`;
}

function formatPlain(value: unknown, t: HitlTranslate): string {
  if (typeof value === "boolean") {
    return resolve(
      t,
      value ? "chat.hitl.bool.true" : "chat.hitl.bool.false",
      value ? "Yes" : "No",
    );
  }
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
      .filter((item) => !isEmpty(item))
      .map((item) => formatPlain(item, t))
      .join(", ");
  }
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([k, v]) => !shouldHide(k, v))
      .map(([k, v]) => `${humanizeArgKey(k)}: ${formatPlain(v, t)}`)
      .join("; ");
  }
  return String(value);
}

function formatKnownString(
  toolName: string,
  key: string,
  raw: string,
  t: HitlTranslate,
): string {
  if (BROWSER_TOOLS.has(toolName) || key === "action") {
    if (key === "action") {
      return resolve(t, `chat.hitl.browser.actions.${raw}`, raw);
    }
    if (key === "level") {
      return resolve(t, `chat.hitl.browser.levels.${raw}`, raw);
    }
    if (key === "direction") {
      return resolve(t, `chat.hitl.browser.directions.${raw}`, raw);
    }
  }
  return raw;
}

function formatArgValue(
  toolName: string,
  key: string,
  value: unknown,
  t: HitlTranslate,
): string {
  if (typeof value === "string") {
    const labelled = formatKnownString(toolName, key, value, t);
    const max = TRUNCATE_KEYS.has(key) ? MAX_TRUNCATED : MAX_HARD;
    return truncate(labelled, max);
  }
  const plain = formatPlain(value, t);
  const max = TRUNCATE_KEYS.has(key) ? MAX_TRUNCATED : MAX_HARD;
  return truncate(plain, max);
}

function argLabel(key: string, t: HitlTranslate): string {
  return resolve(t, `chat.hitl.args.${key}`, humanizeArgKey(key));
}

function stringArg(
  args: Record<string, unknown>,
  ...keys: string[]
): string | undefined {
  for (const key of keys) {
    const value = args[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return undefined;
}

function browserSummary(
  args: Record<string, unknown>,
  t: HitlTranslate,
  toolLabel: string,
): string {
  const action = stringArg(args, "action") ?? "";
  const url = stringArg(args, "url");
  const level = stringArg(args, "level");
  if ((action === "navigate" || action === "open") && url) {
    return resolve(t, "chat.hitl.summaries.openUrl", `Open ${url}`, { url });
  }
  if (action === "new_tab" && url) {
    return resolve(t, "chat.hitl.summaries.openUrl", `Open ${url}`, { url });
  }
  if (action === "screenshot") {
    return resolve(
      t,
      "chat.hitl.summaries.screenshot",
      "Take a screenshot of the current page",
    );
  }
  if (action === "dom_tree" && level === "interactive") {
    return resolve(
      t,
      "chat.hitl.summaries.domTreeInteractive",
      "Read the interactive structure of the current page",
    );
  }
  if (action === "dom_tree") {
    return resolve(
      t,
      "chat.hitl.summaries.domTree",
      "Read the structure of the current page",
    );
  }
  if (action) {
    return resolve(t, `chat.hitl.browser.actions.${action}`, toolLabel);
  }
  return toolLabel;
}

function buildSummary(
  name: string,
  args: Record<string, unknown>,
  t: HitlTranslate,
  toolLabel: string,
  description?: string,
): string {
  const explained = description?.trim();
  if (explained && !isMachineHitlDescription(explained)) return explained;
  if (BROWSER_TOOLS.has(name)) return browserSummary(args, t, toolLabel);
  const command = stringArg(args, "command", "cmd");
  if (SHELL_TOOLS.has(name) && command) {
    return resolve(t, "chat.hitl.summaries.runCommand", `Run: ${command}`, {
      command,
    });
  }
  const path = stringArg(args, "path", "file", "file_path");
  if (name === "write_file" && path) {
    return resolve(t, "chat.hitl.summaries.writeFile", `Write ${path}`, {
      path,
    });
  }
  if (name === "read_file" && path) {
    return resolve(t, "chat.hitl.summaries.readFile", `Read ${path}`, { path });
  }
  if (name === "edit_file" && path) {
    return resolve(t, "chat.hitl.summaries.editFile", `Edit ${path}`, { path });
  }
  const url = stringArg(args, "url");
  if (name === "web_fetch" && url) {
    return resolve(t, "chat.hitl.summaries.fetchUrl", `Fetch ${url}`, { url });
  }
  return toolLabel;
}

export function summarizeHitlAction(
  name: string,
  args: Record<string, unknown> | undefined,
  t: HitlTranslate,
  toolLabel: string,
  description?: string,
): HitlActionView {
  const safeArgs = args && typeof args === "object" ? args : {};
  const rows: HitlArgRow[] = [];
  for (const [key, value] of Object.entries(safeArgs)) {
    if (shouldHide(key, value)) continue;
    const formatted = formatArgValue(name, key, value, t);
    if (!formatted) continue;
    rows.push({
      label: argLabel(key, t),
      value: formatted,
      ...(MONO_KEYS.has(key) ? { mono: true } : {}),
    });
  }
  return {
    toolLabel,
    summary: buildSummary(name, safeArgs, t, toolLabel, description),
    rows,
  };
}
