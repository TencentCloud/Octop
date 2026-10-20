// Native OpenClaw CLI commands for the octopmemory plugin.
//
// The user-facing commands (`status`, `search`, `show`, `reindex`) call
// the long-lived Python bridge directly. Heavy admin operations that
// already exist in `octop-memory` remain available under
// `openclaw octopmemory admin ...` and are forwarded to Python.

import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";

import type { BridgeClient } from "./bridge.js";
import type { OpenClawPluginApi } from "./sdk-shim.js";

interface CommanderProgram {
  command: (def: string) => CommanderCommand;
}

interface CommanderCommand {
  command: (def: string) => CommanderCommand;
  description: (text: string) => CommanderCommand;
  argument: (def: string, description?: string) => CommanderCommand;
  option: (flags: string, description?: string, defaultValue?: unknown) => CommanderCommand;
  allowUnknownOption: (allow?: boolean) => CommanderCommand;
  action: (handler: (...args: unknown[]) => void | Promise<void>) => CommanderCommand;
}

type CliBridge = Pick<BridgeClient, "call"> & {
  stop?: () => Promise<void> | void;
};

export type BridgeProvider = () => Promise<CliBridge>;

interface SearchResultEnvelope {
  hits?: Array<Record<string, unknown>>;
  empty_reason?: string | null;
}

interface GetResultEnvelope {
  path?: string;
  excerpt?: string;
  truncated?: boolean;
  continuation?: { from?: number };
}

export function registerOctopmemoryCli(
  programArg: unknown,
  api: OpenClawPluginApi,
  getBridge?: BridgeProvider,
): void {
  const program = programArg as CommanderProgram;
  const bridgeProvider = getBridge ?? (() => Promise.reject(new Error("octopmemory bridge is unavailable")));

  const root = program.command("octopmemory").description("Inspect, search, and maintain OctopMemory.");

  root
    .command("setup")
    .description("One-click setup: resolve/bootstrap the Python bridge, write config, smoke-test.")
    .option("--quick", "Use zero-dependency defaults (balanced profile, FTS-only).")
    .option("--profile <profile>", "Scenario preset (balanced, low_latency, proactive, privacy, archive, eval).")
    .option("--namespace <ns>", "Memory namespace (default: openclaw__default).")
    .option(
      "--backend <backend>",
      "Storage backend: sqlite (default) or postgres. postgres requires OCTOP_MEMORY_DSN " +
        "already set in this shell's environment — never pass the DSN as a flag.",
    )
    .option("--db-path <path>", "SQLite path (default: ~/.openclaw/octopmemory/<ns>/memory.sqlite — sandbox-visible).")
    .option("--workspace <dir>", "host_files workspace root (default: ~/.openclaw/workspace).")
    .option("--openclaw-config <path>", "openclaw.json path (default: ~/.openclaw/openclaw.json).")
    .option("--bridge-command <path>", "Force a specific octopmemory-bridge executable (skip probing).")
    .option("--no-bootstrap", "Fail instead of installing octop-memory via uv/pipx.")
    .option("--no-restart", "Skip the gateway restart at the end.")
    .option("--dry-run", "Print the resulting openclaw.json instead of writing it.")
    .action(async (opts: unknown) => {
      const { runSetup, SetupError } = await import("./setup.js");
      const o = opts as Record<string, unknown>;
      try {
        await runSetup({
          profile: o.profile as never,
          namespace: o.namespace as string | undefined,
          backend: o.backend as never,
          dbPath: o.dbPath as string | undefined,
          workspace: o.workspace as string | undefined,
          openclawConfigPath: o.openclawConfig as string | undefined,
          bridgeCommand: o.bridgeCommand as string | undefined,
          // commander sets --no-x options to `false`; default true.
          noBootstrap: o.bootstrap === false,
          noRestart: o.restart === false,
          dryRun: Boolean(o.dryRun),
        });
      } catch (err) {
        if (err instanceof SetupError) {
          console.error(`\n❌ setup failed: ${err.message}`);
          process.exitCode = 1;
          return;
        }
        throw err;
      }
    });

  root
    .command("status")
    .description("Show bridge health, active config, and storage counts.")
    .action(async () => {
      await withBridge(bridgeProvider, async (bridge) => {
        const stats = await bridge.call("stats", {});
        console.log(renderStatus(stats));
      });
    });

  root
    .command("search <query>")
    .description("Search OctopMemory via the memory_search contract.")
    .option("-n, --max <n>", "Maximum number of hits", "5")
    .option("--corpus <corpus>", "Corpus: all, memory, sessions, or wiki", "all")
    .action(async (query: unknown, opts: unknown) => {
      await withBridge(bridgeProvider, async (bridge) => {
        const options = opts as { max?: string | number; corpus?: string };
        const result = await bridge.call("memory_search", {
          query: String(query ?? ""),
          maxResults: parsePositiveInt(options.max, 5),
          corpus: options.corpus ?? "all",
        });
        console.log(renderSearchResults(result));
      });
    });

  root
    .command("show <path>")
    .description("Render one memory path via memory_get.")
    .option("--from <line>", "1-based start line")
    .option("--lines <n>", "Number of lines to return")
    .action(async (path: unknown, opts: unknown) => {
      await withBridge(bridgeProvider, async (bridge) => {
        const options = opts as { from?: string | number; lines?: string | number };
        const params: Record<string, unknown> = { path: String(path ?? "") };
        const from = parseOptionalPositiveInt(options.from);
        const lines = parseOptionalPositiveInt(options.lines);
        if (from !== undefined) params.from = from;
        if (lines !== undefined) params.lines = lines;
        const result = await bridge.call("memory_get", params);
        console.log(renderShowResult(result));
      });
    });

  root
    .command("reindex")
    .description("Force a host_files scan (MEMORY.md / memory/*.md).")
    .action(async () => {
      await withBridge(bridgeProvider, async (bridge) => {
        const result = await bridge.call("reindex", {});
        console.log(renderReindexResult(result));
      });
    });

  root
    .command("dashboard")
    .description("Launch the OctopMemory web dashboard (opens in browser).")
    .option("--host <host>", "Bind host", "127.0.0.1")
    .option("--port <port>", "Bind port", "7788")
    .option("--namespace <ns>", "Memory namespace to inspect")
    .option("--no-open", "Do not auto-open the browser")
    .action(async (opts: unknown) => {
      const o = opts as { host?: string; port?: string; namespace?: string; open?: boolean };
      const args = ["dashboard", "--host", o.host ?? "127.0.0.1", "--port", o.port ?? "7788"];
      if (o.namespace) args.push("--namespace", o.namespace);
      if (o.open === false) args.push("--no-open");
      const code = await runOctopMemory(args, api);
      if (code !== 0) {
        process.exitCode = code;
      }
    });

  root
    .command("admin [args...]")
    .description("Forward to the Python octop-memory CLI for advanced maintenance.")
    .allowUnknownOption(true)
    .action(async (args: unknown) => {
      const argv = (args as string[] | undefined) ?? [];
      const code = await runOctopMemory(argv, api);
      if (code !== 0) {
        process.exitCode = code;
      }
    });
}

async function withBridge<T>(bridgeProvider: BridgeProvider, fn: (bridge: CliBridge) => Promise<T>): Promise<T> {
  const bridge = await bridgeProvider();
  try {
    return await fn(bridge);
  } finally {
    await bridge.stop?.();
  }
}

export function renderStatus(raw: unknown): string {
  const stats = raw as Record<string, unknown>;
  const counts = (stats.counts ?? {}) as Record<string, unknown>;
  const config = (stats.config ?? {}) as Record<string, unknown>;
  const recall = (config.recall ?? {}) as Record<string, unknown>;
  const host = stats.host_files as Record<string, unknown> | null | undefined;

  const lines = [
    "OctopMemory status",
    `Namespace: ${stats.namespace ?? "(unknown)"}`,
    `Counts: raw=${counts.raw_events ?? 0} atoms=${counts.atoms ?? 0} entities=${counts.entities ?? 0} dirty_pages=${counts.dirty_pages ?? 0}`,
    `Config: profile=${config.profile ?? "(unknown)"} recall=${recall.mode ?? "(unknown)"}`,
  ];
  if (host) {
    lines.push(
      `HostFiles: host_files=${host.indexed ?? 0} root=${host.root ?? "(unknown)"} last_scan=${host.last_scan_iso ?? "never"}`,
    );
  } else {
    lines.push("HostFiles: disabled");
  }
  return lines.join("\n");
}

export function renderSearchResults(raw: unknown): string {
  const result = raw as SearchResultEnvelope;
  const hits = result.hits ?? [];
  if (hits.length === 0) {
    return `(no hits${result.empty_reason ? `: ${result.empty_reason}` : ""})`;
  }
  return hits
    .map((hit, index) => {
      const snippet = String(hit.snippet ?? "").replace(/\s+/g, " ").trim();
      return `[${index + 1}] ${hit.path ?? "(unknown)"} layer=${hit.layer ?? "?"}\n    ${snippet}`;
    })
    .join("\n");
}

export function renderShowResult(raw: unknown): string {
  const result = raw as GetResultEnvelope;
  const body = String(result.excerpt ?? "");
  if (!result.truncated) {
    return body;
  }
  const next = result.continuation?.from;
  return `${body}\n\n[truncated${next ? `; continue with --from ${next}` : ""}]`;
}

export function renderReindexResult(raw: unknown): string {
  const result = raw as Record<string, unknown>;
  return `Reindex complete: scanned=${result.scanned ?? 0} indexed=${result.indexed ?? 0} removed=${result.removed ?? 0} skipped_binary=${result.skipped_binary ?? 0}`;
}

async function runOctopMemory(argv: string[], api: OpenClawPluginApi): Promise<number> {
  const python = readPython(api);
  const proc: ChildProcessWithoutNullStreams = spawn(
    python,
    ["-m", "octop_memory.adapters.cli", ...argv],
    { stdio: "inherit" } as Parameters<typeof spawn>[2],
  ) as ChildProcessWithoutNullStreams;

  return await new Promise<number>((resolve, reject) => {
    proc.on("error", reject);
    proc.on("exit", (code) => resolve(code ?? 0));
  });
}

function readPython(api: OpenClawPluginApi): string {
  const cfg = (api.pluginConfig ?? {}) as { bridge?: { python?: string } };
  return cfg.bridge?.python ?? "python3";
}

function parsePositiveInt(value: unknown, fallback: number): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseOptionalPositiveInt(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}
