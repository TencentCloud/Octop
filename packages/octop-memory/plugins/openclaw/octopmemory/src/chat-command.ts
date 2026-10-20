// Chat slash command: `/octopmemory <sub>` in a chat session.
//
// The manifest's `commandAliases` entry only participates in *CLI* routing
// (and plugin listings) — OpenClaw's chat pipeline dispatches slash
// commands exclusively through the runtime `api.registerCommand` surface,
// the same one bundled plugins use (e.g. memory-core's `/dreaming`).
// Contract (verified against OpenClaw 2026.6.11 dist):
//   - options: { name, description, acceptsArgs, handler }
//   - handler: async (ctx) => ({ text }) — ctx.args is the raw argument
//     string after the command name.
// Hosts older than the registerCommand surface simply don't expose the
// method; registration is skipped and the CLI/tool paths keep working.

import type { BridgeProvider } from "./cli.js";
import { renderReindexResult, renderSearchResults, renderShowResult, renderStatus } from "./cli.js";
import type { ChatCommandContext, OpenClawPluginApi } from "./sdk-shim.js";

const USAGE = [
  "Usage:",
  "/octopmemory status — namespace, counts, config, host_files",
  "/octopmemory search <query> — search memory (top 5)",
  "/octopmemory show <path> [from] [lines] — read one memory doc",
  "/octopmemory reindex — force a host_files scan",
].join("\n");

/** Parse + dispatch one chat invocation; always resolves to reply text. */
export async function runChatCommand(getBridge: BridgeProvider, rawArgs: string): Promise<string> {
  const tokens = rawArgs.trim().split(/\s+/).filter(Boolean);
  const sub = tokens.shift() ?? "";

  switch (sub) {
    case "":
    case "help":
      return USAGE;
    case "status": {
      const bridge = await getBridge();
      return renderStatus(await bridge.call("stats", {}));
    }
    case "search": {
      if (tokens.length === 0) return "Usage: /octopmemory search <query>";
      const bridge = await getBridge();
      return renderSearchResults(
        await bridge.call("memory_search", { query: tokens.join(" "), maxResults: 5, corpus: "all" }),
      );
    }
    case "show": {
      if (tokens.length === 0) return "Usage: /octopmemory show <path> [from] [lines]";
      const params: Record<string, unknown> = { path: tokens[0] };
      const from = Number.parseInt(tokens[1] ?? "", 10);
      const lines = Number.parseInt(tokens[2] ?? "", 10);
      if (Number.isFinite(from) && from > 0) params.from = from;
      if (Number.isFinite(lines) && lines > 0) params.lines = lines;
      const bridge = await getBridge();
      return renderShowResult(await bridge.call("memory_get", params));
    }
    case "reindex": {
      const bridge = await getBridge();
      return renderReindexResult(await bridge.call("reindex", {}));
    }
    default:
      return `Unknown subcommand "${sub}".\n\n${USAGE}`;
  }
}

/** Register `/octopmemory` as a chat command; no-op on hosts without the surface. */
export function registerChatCommand(api: OpenClawPluginApi, getBridge: BridgeProvider): void {
  if (typeof api.registerCommand !== "function") {
    api.logger?.info?.("[octopmemory] host has no registerCommand surface; /octopmemory chat command unavailable");
    return;
  }
  api.registerCommand({
    name: "octopmemory",
    description: "OctopMemory: status | search <query> | show <path> | reindex",
    acceptsArgs: true,
    handler: async (ctx: ChatCommandContext) => {
      // The shared bridge stays warm across invocations — never stop() it
      // here; it also serves the memory_search/memory_get tools.
      try {
        const args = typeof ctx?.args === "string" ? ctx.args : "";
        return { text: await runChatCommand(getBridge, args) };
      } catch (err) {
        return { text: `octopmemory: ${err instanceof Error ? err.message : String(err)}` };
      }
    },
  });
  // Pre-warm the bridge in the background. A cold first invocation pays the
  // Python spawn (seconds) inside the command handler, which has been seen to
  // race the host's reply-session initialization right after a gateway
  // restart ("reply session initialization conflicted", OpenClaw 2026.6.11).
  // Failures are ignored — the handler surfaces them per invocation.
  void getBridge().catch(() => undefined);
}
