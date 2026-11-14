import type { ChildProcess } from "node:child_process";
import { spawn } from "node:child_process";
import { HEALTH_TIMEOUT_MS, waitForHealth } from "./health";
import { signalTree } from "./process-tree";

/**
 * Owns ONE sidecar process per app launch (§3.1/§3.3). It spawns the Python
 * runtime on an OS-assigned loopback port, waits for ``/api/health``, and tears
 * down only that process tree on exit.
 */

export interface SidecarConfig {
  executable: string;
  args: string[];
  env: NodeJS.ProcessEnv;
  cwd: string;
  port: number;
  /** Fired once, after the child has exited. ``output`` is the retained tail. */
  onExit?: (notice: SidecarExitNotice) => void;
}

export interface SidecarExitNotice {
  code: number | null;
  signal: NodeJS.Signals | null;
  output: string;
}

/** Recent sidecar stdout/stderr kept for a startup failure. Not a second octop.log. */
const OUTPUT_TAIL_MAX = 64 * 1024;

export interface SidecarExit {
  /** ``true`` only when the process exited by itself with code 0 (§6.3). */
  clean: boolean;
  exitCode: number | null;
}

export class SidecarSupervisor {
  private child: ChildProcess | null = null;
  private port: number;
  private tail = "";
  private failed = false;
  private notifiedExit = false;
  private readonly config: SidecarConfig;

  // Plain field assignment (no TS parameter property) keeps this module loadable
  // by Node's strip-only TypeScript mode, so the tests can import it directly.
  constructor(config: SidecarConfig) {
    this.config = config;
    this.port = config.port;
  }

  start(): void {
    const { executable, args, env, cwd } = this.config;
    const options: import("node:child_process").SpawnOptions = {
      cwd,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    };
    if (process.platform !== "win32") options.detached = true;
    this.child = spawn(executable, args, options);
    this.child.stdout?.on("data", (chunk: unknown) => this.note(chunk));
    this.child.stderr?.on("data", (chunk: unknown) => this.note(chunk));
    // An unhandled 'error' (EACCES, ENOENT) becomes an uncaught exception and
    // Electron's native dialog. Record it so the health check fails immediately.
    this.child.on("error", (err: Error) => {
      this.failed = true;
      this.note(`${err.name}: ${err.message}\n`);
      this.notifyExit(null, null);
    });
    this.child.on("exit", (code, signal) => {
      this.notifyExit(code, signal);
    });
  }

  private notifyExit(code: number | null, signal: NodeJS.Signals | null): void {
    if (this.notifiedExit) return;
    this.notifiedExit = true;
    this.config.onExit?.({ code, signal, output: this.tail });
  }

  /** Stdout/stderr retained from this process, capped at 64 KiB. */
  outputTail(): string {
    return this.tail;
  }

  private note(chunk: unknown): void {
    const text = typeof chunk === "string" ? chunk : Buffer.isBuffer(chunk) ? chunk.toString("utf8") : "";
    if (!text) return;
    this.tail = (this.tail + text).slice(-OUTPUT_TAIL_MAX);
  }

  /** Poll only THIS process's port until ``/api/health`` matches the contract. */
  async waitUntilReady(timeoutMs = HEALTH_TIMEOUT_MS): Promise<boolean> {
    if (!this.child) return false;
    return waitForHealth(
      async () => {
        try {
          const res = await fetch(`http://127.0.0.1:${this.port}/api/health`, {
            cache: "no-store",
          });
          if (!res.ok) return { ok: false };
          const body = (await res.json()) as unknown;
          return { ok: res.ok, body };
        } catch {
          return { ok: false };
        }
      },
      {
        timeoutMs,
        onExit: () => !this.isRunning(),
      },
    );
  }

  isRunning(): boolean {
    return (
      this.child !== null &&
      !this.failed &&
      this.child.exitCode === null &&
      this.child.signalCode === null
    );
  }

  /**
   * Graceful stop, then force-kill the whole tree after a grace window (§3.4).
   * The result tells the update flow whether Python really exited on its own:
   * a SIGKILLed (or non-zero) sidecar must never be replaced under (§6.3).
   */
  async stop(graceMs = 5_000): Promise<SidecarExit> {
    const child = this.child;
    if (!child || !this.isRunning()) return { clean: true, exitCode: null };
    signalTree(child, "SIGTERM");
    const exit = await new Promise<{ exited: boolean; code: number | null }>((resolvePromise) => {
      const timer = setTimeout(() => resolvePromise({ exited: false, code: null }), graceMs);
      child.once("exit", (code) => {
        clearTimeout(timer);
        resolvePromise({ exited: true, code });
      });
    });
    if (!exit.exited) {
      signalTree(child, "SIGKILL");
      // taskkill returns before the process is gone. Windows will not delete a
      // directory that is still that process's cwd, so wait for the exit.
      await new Promise((resolvePromise) => {
        if (child.exitCode !== null || child.signalCode !== null) {
          resolvePromise(undefined);
          return;
        }
        const timer = setTimeout(() => resolvePromise(undefined), 2_000);
        child.once("exit", () => {
          clearTimeout(timer);
          resolvePromise(undefined);
        });
      });
      return { clean: false, exitCode: null };
    }
    return { clean: exit.code === 0, exitCode: exit.code };
  }
}
