import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resolveEffectiveConfig } from "./config.ts";

describe("resolveEffectiveConfig", () => {
  it("defaults to the balanced profile", () => {
    const cfg = resolveEffectiveConfig({});

    assert.equal(cfg.profile, "balanced");
    assert.equal(cfg.mode, "self-hosted");
    assert.equal(cfg.recall.mode, "tool_hint");
    assert.equal(cfg.recall.default_max_results, 5);
    assert.equal(cfg.recall.raw_policy, "fallback");
    assert.equal(cfg.capture.agent_end_hook, true);
    assert.equal(cfg.capture.host_files_watcher, true);
    assert.deepEqual(cfg.host_files_allow, ["topics/*.md", "projects/*.md"]);
    assert.deepEqual(cfg.capture.include_roles, ["user", "assistant"]);
  });

  it("applies privacy defaults", () => {
    const cfg = resolveEffectiveConfig({ profile: "privacy" });

    assert.equal(cfg.profile, "privacy");
    assert.equal(cfg.recall.raw_policy, "never");
    assert.equal(cfg.recall.host_files_policy, "off");
    assert.equal(cfg.capture.host_files_watcher, false);
    assert.deepEqual(cfg.capture.include_roles, ["user"]);
    assert.equal(cfg.privacy.store_raw_content, false);
  });

  it("lets explicit overrides win over profile defaults", () => {
    const cfg = resolveEffectiveConfig({
      profile: "privacy",
      recall: { mode: "off", host_files_policy: "include" },
      capture: { host_files_watcher: true, min_message_chars: 10 },
    });

    assert.equal(cfg.profile, "privacy");
    assert.equal(cfg.recall.mode, "off");
    assert.equal(cfg.recall.host_files_policy, "include");
    assert.equal(cfg.capture.host_files_watcher, true);
    assert.equal(cfg.capture.min_message_chars, 10);
    assert.equal(cfg.privacy.store_raw_content, false);
  });

  it("applies archive capture defaults", () => {
    const cfg = resolveEffectiveConfig({ profile: "archive" });

    assert.equal(cfg.recall.raw_policy, "always");
    assert.equal(cfg.recall.default_max_results, 10);
    assert.deepEqual(cfg.capture.include_roles, ["user", "assistant", "tool"]);
    assert.equal(cfg.capture.include_tool_calls, true);
    assert.equal(cfg.capture.include_tool_results, true);
    assert.equal(cfg.compaction.soft_threshold_tokens, 3000);
  });

  it("defaults extract_on_agent_end to true and llm to undefined", () => {
    const cfg = resolveEffectiveConfig({});

    assert.equal(cfg.capture.extract_on_agent_end, true);
    assert.equal(cfg.llm, undefined);
    assert.equal(cfg.extraction, undefined);
  });

  it("passes llm and extraction config through untouched", () => {
    const cfg = resolveEffectiveConfig({
      llm: {
        endpoint: "https://api.deepseek.com/v1",
        model: "deepseek-chat",
        model_heavy: "deepseek-reasoner",
        api_key_env: "MY_LLM_KEY",
      },
      extraction: { promote: false, max_candidates: 10 },
      capture: { extract_on_agent_end: false },
    });

    assert.deepEqual(cfg.llm, {
      endpoint: "https://api.deepseek.com/v1",
      model: "deepseek-chat",
      model_heavy: "deepseek-reasoner",
      api_key_env: "MY_LLM_KEY",
    });
    assert.deepEqual(cfg.extraction, { promote: false, max_candidates: 10 });
    assert.equal(cfg.capture.extract_on_agent_end, false);
  });
});
