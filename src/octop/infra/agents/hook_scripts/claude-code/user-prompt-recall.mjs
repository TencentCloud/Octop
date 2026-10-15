#!/usr/bin/env node
// Claude Code ``UserPromptSubmit`` hook: recall before the model answers.
//
// ``mcp_tool`` hooks are silently skipped for UserPromptSubmit (2.1.263), so this
// is a command hook that calls ``memory_search`` itself and prints the block —
// Claude Code injects the stdout as extra context for this turn.
import fs from "node:fs";
import { callTool, isConfigured, loadConfig, makeLogger } from "../lib/octop-memory-client.mjs";

const log = makeLogger("urecall.claude-code");
const MARKER = "[octop memory search]";
const payload = (() => {
  try {
    const raw = fs.readFileSync(0, "utf8");
    return raw.trim() ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
})();

async function main() {
  const prompt = String(payload.prompt || "").trim();
  if (!prompt) {
    log("skip: empty prompt");
    return;
  }
  const config = loadConfig();
  if (!isConfigured(config)) {
    log("skip: not configured");
    return;
  }
  const maxResults = Number(process.env.OCTOP_RECALL_MAX_RESULTS ?? 5);
  const result = await callTool(config, "memory_search", {
    query: prompt,
    corpus: "atom",
    max_results: maxResults,
  });
  const hits = result.detail?.hits ?? [];
  log(`prompt="${prompt.slice(0, 60)}" hits=${hits.length} http=${result.status}`);
  if (!hits.length) return;
  const lines = [MARKER];
  for (const hit of hits) {
    const when = String(hit.occurred_at || "").slice(0, 19);
    lines.push(`- [${hit.layer}] (${hit.role_hint ?? hit.layer} @ ${when}) ${hit.snippet}`);
  }
  lines.push("若需要原文/证据，用 memory_get(path=…) 读全文；与本次工作无关则忽略。");
  process.stdout.write(lines.join("\n") + "\n");
}

await main();
process.exit(0);
