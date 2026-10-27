import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { join } from "node:path";

/**
 * Spawn the Python sidecar as its own process group (POSIX) and tear it down
 * task-safely: graceful stop first, then the whole tree on timeout (§3.1/§3.4).
 */

export interface SidecarLaunch {
  executable: string;
  args: string[];
  env: NodeJS.ProcessEnv;
  cwd: string;
}

/** Build the child env, pinning loopback + assigned port and never writing config. */
export function buildSidecarEnv(
  base: NodeJS.ProcessEnv,
  options: {
    octopHome: string;
    portableDir: string;
    port: number;
    bindHost: string;
  },
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...base };
  env.OCTOP_HOME = options.octopHome;
  env.OCTOP_GREEN_PACKAGES = joinPortable(options.portableDir);
  env.OCTOP_BIND_HOST = options.bindHost;
  env.OCTOP_PORT = String(options.port);
  env.OCTOP_DESKTOP_SHELL = "1";
  env.PYTHONNOUSERSITE = "1";
  // The launch.py bootstrap handles runtime + .pth itself; an inherited
  // PYTHONPATH would shadow the bundled site-packages, so drop it.
  delete env.PYTHONPATH;
  return env;
}

function joinPortable(portableDir: string): string {
  return join(portableDir, "packages");
}

export function spawnSidecar(launch: SidecarLaunch): ChildProcess {
  const options: SpawnOptions = { cwd: launch.cwd, env: launch.env, stdio: ["ignore", "pipe", "pipe"] };
  if (process.platform !== "win32") {
    options.detached = true; // own process group → kill the whole tree with one signal
  }
  return spawn(launch.executable, launch.args, options);
}

/** Send SIGTERM to the whole process group (POSIX) or taskkill /T (Windows). */
export function signalTree(child: ChildProcess, signal: "SIGTERM" | "SIGKILL"): void {
  if (process.platform === "win32") {
    const flag = signal === "SIGKILL" ? "/F" : "";
    spawn("taskkill", ["/pid", String(child.pid), "/T", flag].filter(Boolean), {
      stdio: "ignore",
    });
    return;
  }
  if (child.pid === undefined) return;
  try {
    process.kill(-child.pid, signal);
  } catch {
    // Group already gone — nothing left to signal.
  }
}

export function isRunning(child: ChildProcess): boolean {
  return child.exitCode === null && child.signalCode === null;
}
