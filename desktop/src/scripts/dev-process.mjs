import { spawn } from "node:child_process";
import { constants } from "node:os";
import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const PS_MAX_BUFFER = 8 * 1024 * 1024;

// `execFile` drops `detached`, so ps would stay in this process's group and a
// terminal SIGINT would kill the inspection mid-snapshot. `spawn` keeps it.
function runPs(args) {
  return new Promise((resolve, reject) => {
    const child = spawn("ps", args, {
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 1_000,
      killSignal: "SIGKILL",
      env: { ...process.env, LC_ALL: "C" },
    });
    const stdout = [];
    const stderr = [];
    let stdoutSize = 0;
    let settled = false;
    function finish(error, value) {
      if (settled) return;
      settled = true;
      if (error) reject(error);
      else resolve(value);
    }
    child.stdout.on("data", (chunk) => {
      stdoutSize += chunk.length;
      if (stdoutSize > PS_MAX_BUFFER) {
        child.kill("SIGKILL");
        return;
      }
      stdout.push(chunk);
    });
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", (error) => finish(error));
    child.once("exit", (code, signal) => {
      if (stdoutSize > PS_MAX_BUFFER) {
        finish(new Error(`ps output exceeded ${PS_MAX_BUFFER} bytes`));
        return;
      }
      if (code === 0) {
        finish(null, Buffer.concat(stdout).toString("utf8"));
        return;
      }
      const detail = Buffer.concat(stderr).toString("utf8").trim();
      finish(new Error(`ps exited ${code ?? signal}${detail ? `: ${detail}` : ""}`));
    });
  });
}

async function processTable() {
  const stdout = await runPs(["-A", "-o", "pid=,ppid=,pgid=,stat=,lstart="]);
  return stdout.trim().split("\n").filter(Boolean).map((line) => {
    const [pid, ppid, pgid, state, ...started] = line.trim().split(/\s+/);
    return { pid: Number(pid), ppid: Number(ppid), pgid: Number(pgid), state, started: started.join(" ") };
  });
}

/** Keep detached descendants even after their parent exits; reject recycled PIDs. */
export function trackTree(table, rootPid, previous, rootStarted) {
  const live = table.filter((row) => !row.state.startsWith("Z"));
  const tracked = new Map(live
    .filter((row) => previous.get(row.pid) === row.started)
    .map((row) => [row.pid, row.started]));
  // The managed command has its own group. Only expand from a verified group
  // member: a bare numeric PGID can be reused after its original leader exits.
  const root = live.find((row) => row.pid === rootPid);
  const expectedStart = rootStarted !== undefined ? rootStarted : previous.get(rootPid);
  const rootReused = root && expectedStart !== undefined && root.started !== expectedStart;
  // A root reaped before the first snapshot (null) leaves its non-detached
  // children behind with pgid === rootPid; adopt them only while the root
  // number itself is still free, so a reused leader is never mistaken for ours.
  const groupKnown = (expectedStart === null && !root) || live.some((row) =>
    row.pgid === rootPid && (tracked.has(row.pid) || (row.pid === rootPid && !rootReused)),
  );
  for (const row of live) {
    if (!rootReused && ((groupKnown && row.pgid === rootPid) || row.pid === rootPid)) {
      tracked.set(row.pid, row.started);
    }
  }
  let added;
  do {
    added = false;
    for (const row of live) {
      if (!tracked.has(row.pid) && tracked.has(row.ppid)) {
        tracked.set(row.pid, row.started);
        added = true;
      }
    }
  } while (added);
  return tracked;
}

/** POSIX development only; the packaged app keeps its own cross-platform lifecycle. */
export async function runDev(command, args, { graceMs = 8_000, forceMs = 2_000, pollMs = 100 } = {}) {
  if (process.platform === "win32") throw new Error("The bash dev runner requires macOS or Linux.");
  // Do not launch an app we cannot inspect and clean up.
  try {
    await processTable();
  } catch (error) {
    throw new Error(`cannot inspect processes with ps (${error.message}); refusing to start an unmanageable dev session`);
  }
  const child = spawn(command, args, { stdio: "inherit", detached: true });
  let exited = false;
  let status = 0;
  let failed = false;
  let stopping = false;
  let forced = false;
  let deadline = Infinity;
  let forceDeadline = Infinity;
  let tracked = new Map();
  let rootStarted;
  let rootTerminated = false;
  const terminated = new Set();

  function report(error) {
    failed = true;
    console.error(`[dev] cleanup failed: ${error.message}`);
  }
  function signal(pid, value) {
    try {
      process.kill(pid, value);
    } catch (error) {
      if (error.code !== "ESRCH") report(error);
    }
  }
  function stop() {
    if (stopping) return;
    stopping = true;
    deadline = Date.now() + graceMs;
    console.error("[dev] stopping development processes…");
  }
  function onSignal() {
    if (stopping) deadline = 0; // second Ctrl+C accelerates, never re-enters cleanup
    else stop();
  }
  const signals = ["SIGINT", "SIGTERM", "SIGHUP"];
  for (const name of signals) process.on(name, onSignal);
  child.once("error", (error) => {
    console.error(`[dev] launch failed: ${error.message}`);
    status = 1;
    exited = true;
    stop();
  });
  child.once("exit", (code, name) => {
    // An explicit terminal stop is success; an unexpected crash remains failure.
    if (!stopping) status = code ?? 128 + (constants.signals[name] ?? 0);
    exited = true;
    stop();
  });

  try {
    while (true) {
      let inspected = false;
      try {
        const table = await processTable();
        if (rootStarted === undefined) {
          // Once waitpid has reaped the child, its number may already belong to
          // somebody else. null means no future snapshot may learn that root.
          rootStarted = exited ? null : table.find((row) => row.pid === child.pid)?.started;
        }
        tracked = trackTree(table, child.pid, tracked, rootStarted);
        inspected = true;
      } catch (error) {
        // A failed sample must not kill a healthy dev session: skip this
        // poll and try again. Only an already-stopping run escalates, because
        // leaving without confirming cleanup would be the outcome we are
        // guarding against.
        if (stopping) report(error);
      }
      if (stopping) {
        if (inspected && exited && tracked.size === 0) break;
        if (!forced && Date.now() >= deadline) {
          forced = true;
          forceDeadline = Date.now() + forceMs;
          console.error("[dev] forcing remaining development processes to exit…");
        }
        // Snapshot before signalling: Python may be reparented as soon as the
        // root dies. Send TERM to the root only once so Electron's second-signal
        // handler cannot accidentally skip graceful sidecar shutdown.
        if (!forced && !exited && child.pid && !rootTerminated) {
          signal(child.pid, "SIGTERM");
          rootTerminated = true;
        }
        // Give Electron its grace window; clean remaining descendants when it
        // exits (including crashes), or force the entire observed tree on timeout.
        // Never signal stale snapshots after ps fails.
        if (inspected && (exited || forced)) {
          for (const [pid, started] of [...tracked].reverse()) {
            const identity = `${pid}:${started}`;
            if (forced || !terminated.has(identity)) {
              signal(pid, forced ? "SIGKILL" : "SIGTERM");
              terminated.add(identity);
            }
          }
        } else if (forced && !exited) {
          child.kill("SIGKILL");
        }
        if (forced && Date.now() >= forceDeadline) {
          report(new Error(`could not confirm process cleanup (PIDs: ${[...tracked.keys()].join(", ") || "unknown"})`));
          break;
        }
      }
      await delay(pollMs);
    }
  } finally {
    for (const name of signals) process.off(name, onSignal);
    // Even an unkillable process must not hold the terminal indefinitely.
    child.unref();
  }
  return failed ? 1 : status;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [command, ...args] = process.argv.slice(2);
  try {
    if (!command) throw new Error("A development command is required.");
    process.exitCode = await runDev(command, args);
  } catch (error) {
    console.error(`[dev] ${error.message}`);
    process.exitCode = 1;
  }
}
