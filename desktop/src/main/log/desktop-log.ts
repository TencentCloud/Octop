import { appendFileSync, mkdirSync, renameSync, rmSync, statSync } from "node:fs";
import { dirname, join } from "node:path";

/**
 * Shell diagnostic log. It lives next to the Python log so a packaged install
 * has one directory to collect: ``<OCTOP_HOME>/logs/desktop.log``.
 *
 * Python keeps its own ``octop.log``. This file is only the Electron shell.
 */

const DEFAULT_MAX_BYTES = 5 * 1024 * 1024;

export function desktopLogPath(octopHome: string): string {
  return join(octopHome, "logs", "desktop.log");
}

export interface DesktopLog {
  /** Absolute path this logger appends to. Empty until a file is installed. */
  readonly path: string;
  info(message: string): void;
  warn(message: string): void;
  error(message: string): void;
}

export function openDesktopLog(filePath: string, maxBytes = DEFAULT_MAX_BYTES): DesktopLog {
  const write = (level: "INFO" | "WARN" | "ERROR", message: string): void => {
    const stamp = new Date().toISOString();
    const lines = message.replaceAll("\r\n", "\n").replaceAll("\r", "\n").split("\n");
    const body = `${lines.map((line) => `${stamp} ${level} ${line}`).join("\n")}\n`;
    try {
      mkdirSync(dirname(filePath), { recursive: true });
      rotate(filePath, maxBytes);
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

function rotate(filePath: string, maxBytes: number): void {
  if (maxBytes <= 0) return;
  let size = 0;
  try {
    size = statSync(filePath).size;
  } catch {
    return;
  }
  if (size < maxBytes) return;
  const previous = `${filePath}.1`;
  rmSync(previous, { force: true });
  renameSync(filePath, previous);
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

/** Open ``<octopHome>/logs/desktop.log`` and send later ``desktopLog()`` calls there. */
export function installDesktopLog(octopHome: string): DesktopLog {
  active = openDesktopLog(desktopLogPath(octopHome));
  return active;
}

/** The installed file logger, or a console-only logger before install. */
export function desktopLog(): DesktopLog {
  return active;
}
