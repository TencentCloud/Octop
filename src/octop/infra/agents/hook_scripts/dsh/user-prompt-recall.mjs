#!/usr/bin/env node
// DSH ``UserPromptSubmit`` hook: search memory for the incoming prompt and inject
// the hits as extra context.
//
// The bridge reads context only from structured output, so the answer must be the
// ``hookSpecificOutput`` object below — plain stdout is silently dropped (unlike
// Claude Code, where the claude-code entry script's stdout becomes context).
//
// The store's full-text search is conjunctive: every term must match, so a long
// prompt whose tail is an instruction ("请只回答…") widens the query until nothing
// matches. Try the first sentence, then its shorter prefixes, then the whole
// prompt; only widen the layer to raw events as a last resort.
import { callTool, isConfigured, makeLogger, readStdinJson } from "../lib/octop-memory-client.mjs";
import { resolveConfig } from "./memory-target.mjs";

const MARKER = "[octop memory search] related memories from this workspace, most relevant first:";
const FOOTER = "若需要原文/证据，用 memory_get(path=…) 读全文；与本次工作无关则忽略。";

function candidateQueries(text) {
  const candidates = [];
  const push = (value) => {
    const candidate = String(value || "").trim();
    if (candidate && !candidates.includes(candidate)) candidates.push(candidate);
  };
  const firstSentence =
    text.split(/[。！？!?；;\n\r]+/).map((part) => part.trim()).find(Boolean) ?? text;
  push(firstSentence);
  push(firstSentence.slice(0, 60));
  push(firstSentence.slice(0, 30));
  push(text.slice(0, 60));
  return candidates;
}

async function main() {
  const log = makeLogger("urecall.dsh");
  const prompt = String(readStdinJson(log).prompt || "").trim();
  if (!prompt) {
    log("skip: empty prompt");
    return;
  }
  const config = resolveConfig();
  if (!isConfigured(config)) {
    log("skip: not configured");
    return;
  }

  const maxResults = Number(process.env.OCTOP_RECALL_MAX_RESULTS ?? 5);
  const candidates = candidateQueries(prompt);
  let hits = [];
  let query = candidates[0];
  let corpus = "atom";
  for (const candidate of candidates) {
    const result = await callTool(config, "memory_search", {
      query: candidate,
      corpus: corpus,
      max_results: maxResults,
    });
    hits = result.detail?.hits ?? [];
    if (hits.length) {
      query = candidate;
      break;
    }
  }
  if (!hits.length) {
    // Fresh facts stay in the raw layer until extraction promotes them.
    corpus = "all";
    const result = await callTool(config, "memory_search", {
      query: candidates[0],
      corpus: corpus,
      max_results: maxResults,
    });
    hits = result.detail?.hits ?? [];
  }
  log(
    `prompt="${prompt.slice(0, 60)}" query="${query.slice(0, 40)}" ` +
      `corpus=${corpus} hits=${hits.length}`,
  );
  if (!hits.length) return;

  const lines = [MARKER];
  for (const hit of hits) {
    const when = String(hit.occurred_at || "").slice(0, 19);
    lines.push(`- [${hit.layer}] (${hit.role_hint ?? hit.layer}${when ? ` @ ${when}` : ""}) ${hit.snippet}`);
  }
  lines.push(FOOTER);
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "UserPromptSubmit",
        additionalContext: lines.join("\n"),
      },
    }),
  );
}

await main();
process.exit(0);
