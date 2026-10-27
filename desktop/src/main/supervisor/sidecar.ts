import type { ChildProcess } from "node:child_process";
import { spawn } from "node:child_process";
import { waitForHealth } from "./health";
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
}

export interface SidecarExit {
  /** ``true`` only when the process exited by itself with code 0 (§6.3). */
  clean: boolean;
  exitCode: number | null;
}

export class SidecarSupervisor {
  private child: ChildProcess | null = null;
  private port: number;
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
    this.child.stdout?.on("data", () => undefined);
    this.child.stderr?.on("data", () => undefined);
  }

  /** Poll only THIS process's port until ``/api/health`` matches the contract. */
  async waitUntilReady(timeoutMs = 30_000): Promise<boolean> {
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
    return this.child !== null && this.child.exitCode === null && this.child.signalCode === null;
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
      return { clean: false, exitCode: null };
    }
    return { clean: exit.code === 0, exitCode: exit.code };
  }
}
