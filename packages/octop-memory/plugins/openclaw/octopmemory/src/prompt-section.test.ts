import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildPromptSection, makePromptSectionBuilder } from "./prompt-section.ts";

const baseCtx = {
  availableTools: new Set(["memory_search", "memory_get"]),
  citationsMode: "on" as const,
};

describe("prompt section recall modes", () => {
  it("defaults to tool_hint mode", () => {
    const lines = buildPromptSection(baseCtx);

    assert.equal(lines[0], "## Memory Recall");
    assert.match(lines.join("\n"), /memory_search/);
    assert.match(lines.join("\n"), /memory_get/);
  });

  it("off mode omits the memory prompt section entirely", () => {
    const build = makePromptSectionBuilder({ mode: "off" });

    assert.deepEqual(build(baseCtx), []);
  });

  it("tool_hint mode injects tool guidance without preloaded memory snippets", () => {
    const build = makePromptSectionBuilder({ mode: "tool_hint" });
    const text = build(baseCtx).join("\n");

    assert.match(text, /Use `memory_search`/);
    assert.doesNotMatch(text, /Relevant memories:/);
  });

  it("hybrid mode injects hybrid tool guidance", () => {
    const build = makePromptSectionBuilder({ mode: "hybrid" });
    const text = build(baseCtx).join("\n");

    assert.match(text, /Hybrid auto-recall is configured/);
    assert.match(text, /use `memory_search`/i);
  });

  it("hybrid mode injects query context when the host provides it", () => {
    const build = makePromptSectionBuilder({ mode: "hybrid" });
    const text = build({
      ...baseCtx,
      query: "What did we decide about billing retries?",
      threadId: "thread-123",
      sessionId: "session-abc",
      userId: "user-9",
      agentId: "agent-main",
    }).join("\n");

    assert.match(text, /Query context: What did we decide about billing retries\?/);
    assert.match(text, /Scope: thread_id=thread-123, session_id=session-abc, user_id=user-9, agent_id=agent-main/);
  });

  it("tool_hint mode ignores query context and stays tool-hint-only", () => {
    const build = makePromptSectionBuilder({ mode: "tool_hint" });
    const text = build({
      ...baseCtx,
      query: "What did we decide about billing retries?",
      threadId: "thread-123",
    }).join("\n");

    assert.doesNotMatch(text, /Query context:/);
    assert.doesNotMatch(text, /Scope:/);
    assert.doesNotMatch(text, /Relevant memories:/);
  });

  it("hybrid mode renders prefetched recall results within the prompt budget", () => {
    const build = makePromptSectionBuilder({ mode: "hybrid", maxPromptChars: 120 });
    const text = build({
      ...baseCtx,
      query: "billing retries",
      recallResults: [
        {
          path: "atom/atm_billing.md",
          layer: "atom",
          snippet: "Billing retries use exponential backoff and stop after the third attempt.",
        },
        {
          path: "raw/2026-06-16/evt_1.md",
          layer: "raw",
          snippet: "A much longer raw transcript that should be omitted by the budget once the first result is rendered.",
        },
      ],
    }).join("\n");

    assert.match(text, /Relevant memories:/);
    assert.match(text, /Hybrid auto-recall has preloaded relevant memories below/);
    assert.match(text, /Billing retries use exponential backoff/);
    assert.match(text, /Source: atom\/atm_billing\.md/);
    assert.match(text, /additional memories omitted by recall\.max_prompt_chars budget/);
  });
});
