#!/usr/bin/env node
// Cursor ``beforeSubmitPrompt`` hook: recall before the model answers.
//
// Cursor's payload carries ``prompt`` (and ``conversation_id``/``cwd``); its hook
// output understands ``additionalContext``, so the recalled block is injected for
// this turn.
import fs from "node:fs";
import { callTool, isConfigured, loadConfig, makeLogger } from "../lib/octop-memory-client.mjs";

const log = makeLogger("urecall.cursor");
const MARKER = "[octop memory search]";

async function main() {
  let payload = {};
  try {
    const raw = fs.readFileSync(0, "utf8");
    if (raw.trim()) payload = JSON.parse(raw);
  } catch {
    log("stdin-not-json");
  }
  const prompt = String(payload.prompt || payload.user_message || "").trim();
  if (!prompt) {
    log("skip: empty prompt");
    return;
  }
  const config = loadConfig();
  if (!isConfigured(config)) {
    log("skip: not configured");
    return;
  }
  const result = await callTool(config, "memory_search", {
    query: prompt,
    corpus: "atom",
    max_results: Number(process.env.OCTOP_RECALL_MAX_RESULTS ?? 5),
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
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "beforeSubmitPrompt",
        additionalContext: lines.join("\n"),
      },
    }) + "\n",
  );
}

await main();
process.exit(0);
