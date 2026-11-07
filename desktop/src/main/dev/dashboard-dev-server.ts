import { spawn, type ChildProcess } from "node:child_process";
import { access } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

/**
 * Local Dashboard dev server. The packaged shell serves a static build from
 * ``octop://app``. ``pnpm dev`` instead runs Vite and loads that origin, so
 * edits to ``dashboard/`` hot-reload without a production rebuild.
 */

const DEFAULT_PORT = 5173;
const READY_TIMEOUT_MS = 90_000;

export interface DashboardDev {
  sourceDir: string;
  port: number;
}

interface ViteExit {
  code: number | null;
  signal: NodeJS.Signals | null;
}

export function dashboardDevOrigin(port: number): string {
  return `http://127.0.0.1:${port}`;
}

/**
 * Node on Windows rejects ``spawn`` of a ``.cmd`` shim with ``EINVAL``.
 * ``cmd.exe /d /s /c`` is the launcher that actually runs ``vite.cmd``.
 */
export function viteCommand(launch: { command: string; args: string[] }): {
  command: string;
  args: string[];
} {
  if (process.platform !== "win32") return { command: launch.command, args: launch.args };
  const comspec = process.env.ComSpec?.trim() || "cmd.exe";
  return { command: comspec, args: ["/d", "/s", "/c", launch.command, ...launch.args] };
}

/** ``null`` when this launch should keep serving the static Dashboard. */
export function readDashboardDev(env: NodeJS.ProcessEnv): DashboardDev | null {
  if (env.OCTOP_DASHBOARD_DEV !== "1") return null;
  const sourceDir = (env.OCTOP_DASHBOARD_SOURCE ?? "").trim();
  if (!sourceDir) {
    throw new Error("OCTOP_DASHBOARD_DEV=1 requires OCTOP_DASHBOARD_SOURCE");
  }
  const raw = (env.OCTOP_DASHBOARD_DEV_PORT ?? "").trim();
  const port = raw === "" ? DEFAULT_PORT : Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`invalid OCTOP_DASHBOARD_DEV_PORT: ${env.OCTOP_DASHBOARD_DEV_PORT}`);
  }
  return { sourceDir, port };
}

export function viteLaunch(options: {
  sourceDir: string;
  port: number;
  apiPort: number;
  baseEnv: NodeJS.ProcessEnv;
}): { command: string; args: string[]; cwd: string; env: NodeJS.ProcessEnv } {
  const bin = process.platform === "win32" ? "vite.cmd" : "vite";
  return {
    command: join(options.sourceDir, "node_modules", ".bin", bin),
    args: ["--host", "127.0.0.1", "--port", String(options.port), "--strictPort"],
    cwd: options.sourceDir,
    env: {
      ...options.baseEnv,
      VITE_API_PORT: String(options.apiPort),
      VITE_DEV_PORT: String(options.port),
      VITE_HMR_CLIENT_PORT: String(options.port),
    },
  };
}

/** Resolve once the dev server answers. 5xx and connection errors keep waiting. */
export async function waitForDevServer(
  url: string,
  timeoutMs = READY_TIMEOUT_MS,
  exited?: () => ViteExit | null,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "no response";
  while (Date.now() < deadline) {
    const gone = exited?.();
    if (gone) {
      throw new Error(`vite exited code=${gone.code ?? "null"} signal=${gone.signal ?? "null"}`);
    }
    try {
      const response = await fetch(url, { redirect: "manual" });
      if (response.status < 500) return;
      lastError = `HTTP ${response.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await delay(250);
  }
  throw new Error(`dashboard dev server did not become ready (${lastError})`);
}

let child: ChildProcess | null = null;

export async function startDashboardDevServer(options: {
  sourceDir: string;
  port: number;
  apiPort: number;
}): Promise<void> {
  if (child) return;
  const launch = viteLaunch({ ...options, baseEnv: process.env });
  try {
    await access(launch.command);
  } catch {
    throw new Error(`${launch.command} is missing — run npm install in dashboard/`);
  }

  const command = viteCommand(launch);
  const proc = spawn(command.command, command.args, {
    cwd: launch.cwd,
    env: launch.env,
    stdio: "inherit",
    windowsHide: true,
  });
  child = proc;
  let exit: ViteExit | null = null;
  proc.on("exit", (code, signal) => {
    exit = { code, signal };
    if (child === proc) child = null;
  });

  try {
    await waitForDevServer(dashboardDevOrigin(options.port), READY_TIMEOUT_MS, () => exit);
  } catch (err) {
    stopDashboardDevServer();
    throw err;
  }
}

export function stopDashboardDevServer(): void {
  const proc = child;
  child = null;
  if (!proc || proc.exitCode !== null) return;
  proc.kill("SIGTERM");
}
