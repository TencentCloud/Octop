// JSON-RPC 2.0 client over a child-process stdin/stdout pair.
//
// Spawns the Python `octopmemory-bridge` once per plugin instance and
// keeps a single long-lived subprocess. Requests are line-framed JSON
// objects; responses arrive in-order on stdout (one per request).
//
// Concurrency: requests are queued. The bridge is single-threaded by
// design (M0..M5 assume one connection per Memory). For higher
// throughput we'd spawn additional bridges per agent — but per
// OpenClaw plugin lifecycle there's exactly one Memory instance, so
// one bridge is the right shape.

import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { createInterface } from "node:readline";

export interface BridgeOptions {
  /**
   * Explicit bridge executable — the `octopmemory-bridge` console
   * script registered by the Python package. When set it is spawned
   * directly (no `python -m` prefix), which decouples us from any
   * specific interpreter path. `setup` resolves this from the uv/pipx
   * tool env. Takes precedence over `python`.
   */
  command?: string;
  /** Python interpreter (default: `python3`). Used only when `command` is unset. */
  python?: string;
  /** Memory namespace, e.g. `openclaw__a3f2c891`. */
  namespace: string;
  /**
   * Storage backend (default: sqlite). When `"postgres"`, the bridge
   * reads the connection string from `OCTOP_MEMORY_DSN` in its own
   * environment — inherited automatically from this Node process since
   * `spawn()` is called without an explicit `env` override below. The
   * DSN itself must never be threaded through `BridgeOptions`/argv: it
   * embeds a password and argv is visible in process listings.
   */
  backend?: "sqlite" | "postgres";
  /** Optional explicit SQLite path. */
  dbPath?: string;
  /** Optional OpenClaw workspace root for host_files indexing. */
  hostFilesRoot?: string;
  /** Additional relative markdown globs to index under hostFilesRoot. */
  hostFilesAllow?: string[];
  /** Optional host_files scan interval in seconds. */
  hostFilesPollInterval?: number;
  /** Runtime policy passed to the Python bridge. */
  config?: Record<string, unknown>;
  /** Stderr log verbosity for the subprocess. */
  logLevel?: "debug" | "info" | "warning" | "error";
  /**
   * Max ms to wait for the initial handshake. Defaults to 5000.
   * If the bridge fails to come up within this we throw on `start()`.
   */
  spawnTimeoutMs?: number;
  /**
   * Optional callback for the subprocess stderr stream. The plugin
   * shell wires this to OpenClaw's logger. Defaults to no-op.
   */
  onStderr?: (line: string) => void;
}

export interface JsonRpcError {
  code: number;
  message: string;
}

export class JsonRpcRemoteError extends Error {
  readonly code: number;

  constructor(code: number, message: string) {
    super(message);
    this.code = code;
    this.name = "JsonRpcRemoteError";
  }
}

interface PendingRequest {
  resolve: (result: unknown) => void;
  reject: (err: Error) => void;
  method: string;
}

type AnyRecord = Record<string, unknown>;

/** The Python module spawned via `python -m` when no `command` is set. */
export const BRIDGE_MODULE = "octop_memory.adapters.bridge.server";

/**
 * Bridge-specific CLI args (namespace, log-level, db-path, host_files,
 * config-json) — without any launch prefix. Shared by both spawn
 * shapes: `octopmemory-bridge <args>` and `python -m MODULE <args>`.
 */
export function buildBridgeOnlyArgs(opts: BridgeOptions): string[] {
  const args = ["--namespace", opts.namespace, "--log-level", opts.logLevel ?? "info"];
  if (opts.backend && opts.backend !== "sqlite") {
    args.push("--backend", opts.backend);
  }
  if (opts.dbPath) {
    args.push("--db-path", opts.dbPath);
  }
  if (opts.hostFilesRoot) {
    args.push("--host-files-root", opts.hostFilesRoot);
    for (const pattern of opts.hostFilesAllow ?? []) {
      args.push("--host-files-allow", pattern);
    }
    if (opts.hostFilesPollInterval !== undefined) {
      args.push("--host-files-poll-interval", String(opts.hostFilesPollInterval));
    }
  }
  if (opts.config) {
    args.push("--config-json", JSON.stringify(opts.config));
  }
  return args;
}

/**
 * Full `python -m` argv (module + bridge args). Kept for the
 * interpreter-launch path and for callers/tests that expect the
 * module form.
 */
export function buildBridgeArgs(opts: BridgeOptions): string[] {
  return ["-m", BRIDGE_MODULE, ...buildBridgeOnlyArgs(opts)];
}

/**
 * Resolve how to spawn the bridge. Prefer the `octopmemory-bridge`
 * console script (decoupled from interpreter path); otherwise launch
 * `python -m MODULE`.
 */
export function resolveBridgeSpawn(opts: BridgeOptions): { command: string; args: string[] } {
  if (opts.command) {
    return { command: opts.command, args: buildBridgeOnlyArgs(opts) };
  }
  return { command: opts.python ?? "python3", args: buildBridgeArgs(opts) };
}

export class BridgeClient {
  private readonly opts: BridgeOptions;
  private proc: ChildProcessWithoutNullStreams | null = null;
  private nextId = 1;
  private pending = new Map<number, PendingRequest>();
  private startPromise: Promise<void> | null = null;

  constructor(opts: BridgeOptions) {
    this.opts = opts;
  }

  /**
   * Spawn the subprocess and run a handshake. Resolves once the
   * server confirms its protocol version. Subsequent `call()`s can
   * be made immediately.
   *
   * Idempotent: calling `start()` more than once returns the same
   * promise.
   */
  start(): Promise<void> {
    if (this.startPromise) return this.startPromise;

    this.startPromise = (async () => {
      const { command, args } = resolveBridgeSpawn(this.opts);
      const proc = spawn(command, args, { stdio: ["pipe", "pipe", "pipe"] });
      this.proc = proc;
      this.attachReader(proc);

      // Race the handshake against a timeout so a missing/broken
      // bridge fails loudly rather than hanging the plugin load.
      const handshake = this.call("handshake", { client_version: "1.0" });
      const timeout = new Promise<never>((_, reject) => {
        setTimeout(() => {
          reject(new Error(`octopmemory-bridge handshake timed out after ${this.opts.spawnTimeoutMs ?? 5000}ms`));
        }, this.opts.spawnTimeoutMs ?? 5000);
      });
      await Promise.race([handshake, timeout]);
    })();

    this.startPromise.catch(() => {
      // If start() failed, clear it so caller can retry.
      this.startPromise = null;
      this.proc?.kill();
      this.proc = null;
    });

    return this.startPromise;
  }

  /**
   * Issue a JSON-RPC request and resolve with the `result` field.
   * Rejects with :class:`JsonRpcRemoteError` on a server error
   * envelope, or a plain `Error` on transport failure.
   */
  call(method: string, params: AnyRecord): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const proc = this.proc;
      if (!proc) {
        reject(new Error("BridgeClient: subprocess not running; call start() first"));
        return;
      }
      const id = this.nextId++;
      this.pending.set(id, { resolve, reject, method });
      const envelope = JSON.stringify({ jsonrpc: "2.0", id, method, params });
      proc.stdin.write(envelope + "\n", (err) => {
        if (err) {
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  /** Stop the subprocess; subsequent calls reject. */
  async stop(): Promise<void> {
    const proc = this.proc;
    if (!proc) return;
    proc.stdin.end();
    await new Promise<void>((resolve) => {
      const onExit = () => resolve();
      proc.once("exit", onExit);
      // 1s grace for the loop to drain, then SIGTERM.
      setTimeout(() => {
        if (this.proc === proc) proc.kill();
      }, 1000);
    });
    for (const pending of this.pending.values()) {
      pending.reject(new Error("BridgeClient stopped before response"));
    }
    this.pending.clear();
    this.proc = null;
    this.startPromise = null;
  }

  // ------------------------------------------------------------------
  // Internal: stdout reader + stderr forwarder
  // ------------------------------------------------------------------

  private attachReader(proc: ChildProcessWithoutNullStreams): void {
    const rl = createInterface({ input: proc.stdout });
    rl.on("line", (line) => this.handleLine(line));
    rl.on("close", () => this.failAllPending(new Error("octopmemory-bridge stdout closed")));

    if (this.opts.onStderr) {
      const errRl = createInterface({ input: proc.stderr });
      errRl.on("line", this.opts.onStderr);
    }

    proc.on("error", (err) => this.failAllPending(err));
    proc.on("exit", (code, signal) => {
      this.failAllPending(
        new Error(`octopmemory-bridge exited (code=${code} signal=${signal})`),
      );
    });
  }

  private handleLine(line: string): void {
    let msg: AnyRecord;
    try {
      msg = JSON.parse(line) as AnyRecord;
    } catch {
      // Non-JSON line on stdout — should never happen, but don't
      // crash the plugin if the subprocess prints something unexpected.
      return;
    }
    const id = msg.id as number | undefined;
    if (typeof id !== "number") return;
    const pending = this.pending.get(id);
    if (!pending) return;
    this.pending.delete(id);
    if (msg.error) {
      const err = msg.error as JsonRpcError;
      pending.reject(new JsonRpcRemoteError(err.code, err.message));
      return;
    }
    pending.resolve(msg.result);
  }

  private failAllPending(err: Error): void {
    for (const pending of this.pending.values()) {
      pending.reject(err);
    }
    this.pending.clear();
  }
}
