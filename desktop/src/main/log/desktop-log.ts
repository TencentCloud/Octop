import { appendFileSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { basename, dirname, extname, join } from "node:path";
import { gzipSync } from "node:zlib";

/**
 * Shell diagnostic log. It lives in its own directory next to the Python log:
 * ``<OCTOP_HOME>/logs/desktop/desktop.log``.
 *
 * Rotation matches ``octop.log``: roll at local midnight and at 100 MiB,
 * keep ``desktop.YYYY-MM-DD.log`` (``.001`` when the same day rolls again),
 * gzip older rotated files on the next cycle, and delete files older than 14 days.
 * ``OCTOP_LOG_MAX_BYTES``, ``OCTOP_LOG_RETENTION_DAYS``, and ``OCTOP_LOG_COMPRESS``
 * apply the same way as the Python log.
 *
 * Python keeps its own ``octop.log``. This file is only the Electron shell.
 */

const DEFAULT_MAX_BYTES = 100 * 1024 * 1024;
const DEFAULT_RETENTION_DAYS = 14;

export function desktopLogPath(octopHome: string): string {
  return join(octopHome, "logs", "desktop", "desktop.log");
}

export interface DesktopLogOptions {
  maxBytes?: number;
  retentionDays?: number;
  compressRotated?: boolean;
}

export interface DesktopLog {
  /** Absolute path this logger appends to. Empty until a file is installed. */
  readonly path: string;
  info(message: string): void;
  warn(message: string): void;
  error(message: string): void;
}

export function openDesktopLog(filePath: string, options: DesktopLogOptions = {}): DesktopLog {
  const maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
  const retentionDays = options.retentionDays ?? DEFAULT_RETENTION_DAYS;
  const compressRotated = options.compressRotated ?? true;
  const stem = basename(filePath, extname(filePath));
  const dir = dirname(filePath);
  try {
    mkdirSync(dir, { recursive: true });
    purgeStaleLogs(dir, stem, retentionDays);
    if (compressRotated) delaycompressRotatedLogs(dir, stem, null);
  } catch {
    // A log failure must not take down the shell.
  }
  const write = (level: "INFO" | "WARN" | "ERROR", message: string): void => {
    const stamp = new Date().toISOString();
    const lines = message.replaceAll("\r\n", "\n").replaceAll("\r", "\n").split("\n");
    const body = `${lines.map((line) => `${stamp} ${level} ${line}`).join("\n")}\n`;
    try {
      mkdirSync(dir, { recursive: true });
      rotate(filePath, stem, maxBytes, compressRotated);
      appendFileSync(filePath, body);
    } catch {
      // A log failure must not take down the shell.
    }
  };
  return {
    path: filePath,
    info(message) {
      write("INFO", message);
      console.info(message);
    },
    warn(message) {
      write("WARN", message);
      console.warn(message);
    },
    error(message) {
      write("ERROR", message);
      console.error(message);
    },
  };
}

function rotate(filePath: string, stem: string, maxBytes: number, compressRotated: boolean): void {
  let size = 0;
  let mtime = new Date();
  try {
    const info = statSync(filePath);
    size = info.size;
    mtime = info.mtime;
  } catch {
    return;
  }
  const staleDay = localDateStamp(mtime) !== localDateStamp(new Date());
  const oversize = maxBytes > 0 && size >= maxBytes;
  if (!staleDay && !oversize) return;
  const dir = dirname(filePath);
  const dest = rotatedDest(dir, stem, localDateStamp(mtime));
  renameSync(filePath, dest);
  if (compressRotated) delaycompressRotatedLogs(dir, stem, dest);
}

function rotatedDest(dir: string, stem: string, date: string): string {
  const named = join(dir, `${stem}.${date}.log`);
  if (!exists(named) && !exists(`${named}.gz`)) return named;
  let index = 1;
  while (true) {
    const candidate = `${named}.${String(index).padStart(3, "0")}`;
    if (!exists(candidate) && !exists(`${candidate}.gz`)) return candidate;
    index += 1;
  }
}

function delaycompressRotatedLogs(dir: string, stem: string, keep: string | null): void {
  const plains = listRotated(dir, stem).filter((entry) => !entry.endsWith(".gz"));
  if (plains.length === 0) return;
  const keepPath =
    keep ??
    plains.reduce((best, entry) => (mtimeMs(entry) > mtimeMs(best) ? entry : best));
  for (const entry of plains) {
    if (entry === keepPath) continue;
    gzipRotatedLog(entry);
  }
}

function gzipRotatedLog(path: string): void {
  if (path.endsWith(".gz")) return;
  const gzPath = `${path}.gz`;
  if (exists(gzPath)) return;
  try {
    writeFileSync(gzPath, gzipSync(readFileSync(path), { level: 6 }));
    unlinkSync(path);
  } catch {
    try {
      unlinkSync(gzPath);
    } catch {
      // Leave the plain file in place when compression fails.
    }
  }
}

function purgeStaleLogs(dir: string, stem: string, retentionDays: number): void {
  if (retentionDays <= 0) return;
  const cutoff = Date.now() - retentionDays * 86_400_000;
  for (const entry of listRotated(dir, stem)) {
    try {
      if (statSync(entry).mtimeMs < cutoff) rmSync(entry, { force: true });
    } catch {
      // A single stale file must not block the rest of the purge.
    }
  }
}

function listRotated(dir: string, stem: string): string[] {
  let names: string[] = [];
  try {
    names = readdirSync(dir);
  } catch {
    return [];
  }
  const pattern = rotatedNamePattern(stem);
  return names.filter((name) => pattern.test(name)).map((name) => join(dir, name));
}

function rotatedNamePattern(stem: string): RegExp {
  return new RegExp(`^${escapeRegExp(stem)}\\.\\d{4}-\\d{2}-\\d{2}\\.log(?:\\.\\d{3})?(?:\\.gz)?$`);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function localDateStamp(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function mtimeMs(path: string): number {
  try {
    return statSync(path).mtimeMs;
  } catch {
    return 0;
  }
}

function exists(path: string): boolean {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

/** Move ``logs/desktop.log`` from before the ``logs/desktop/`` directory existed. */
function migrateLegacyDesktopLog(octopHome: string): void {
  const logsDir = join(octopHome, "logs");
  const legacy = join(logsDir, "desktop.log");
  const legacyBackup = join(logsDir, "desktop.log.1");
  if (!exists(legacy) && !exists(legacyBackup)) return;
  const destDir = join(logsDir, "desktop");
  const dest = join(destDir, "desktop.log");
  try {
    mkdirSync(destDir, { recursive: true });
    if (exists(legacy) && !exists(dest)) renameSync(legacy, dest);
    if (exists(legacyBackup)) {
      const rotated = rotatedDest(destDir, "desktop", localDateStamp(statSync(legacyBackup).mtime));
      renameSync(legacyBackup, rotated);
    }
  } catch {
    // Migration must not take down the shell.
  }
}

function desktopLogOptionsFromEnv(): DesktopLogOptions {
  return {
    maxBytes: parseMaxBytes(process.env.OCTOP_LOG_MAX_BYTES),
    retentionDays: parseRetentionDays(process.env.OCTOP_LOG_RETENTION_DAYS),
    compressRotated: parseCompress(process.env.OCTOP_LOG_COMPRESS),
  };
}

function parseMaxBytes(raw: string | undefined): number {
  const parsed = parseEnvInt(raw, DEFAULT_MAX_BYTES);
  return Math.max(0, parsed);
}

function parseRetentionDays(raw: string | undefined): number {
  return parseEnvInt(raw, DEFAULT_RETENTION_DAYS);
}

function parseEnvInt(raw: string | undefined, fallback: number): number {
  const text = raw?.trim() ?? "";
  if (text === "" || !/^-?\d+$/.test(text)) return fallback;
  const value = Number(text);
  if (!Number.isSafeInteger(value)) return fallback;
  return value;
}

function parseCompress(raw: string | undefined): boolean {
  const text = (raw?.trim() || "1").toLowerCase();
  return !["0", "false", "no", "off"].includes(text);
}

const consoleLog: DesktopLog = {
  path: "",
  info(message) {
    console.info(message);
  },
  warn(message) {
    console.warn(message);
  },
  error(message) {
    console.error(message);
  },
};

let active: DesktopLog = consoleLog;

/** Open ``<octopHome>/logs/desktop/desktop.log`` and send later ``desktopLog()`` calls there. */
export function installDesktopLog(octopHome: string): DesktopLog {
  migrateLegacyDesktopLog(octopHome);
  active = openDesktopLog(desktopLogPath(octopHome), desktopLogOptionsFromEnv());
  return active;
}

/** The installed file logger, or a console-only logger before install. */
export function desktopLog(): DesktopLog {
  return active;
}
