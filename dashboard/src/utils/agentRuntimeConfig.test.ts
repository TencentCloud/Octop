import { describe, expect, it } from "vitest";
import {
  buildAgentRuntimeRequest,
  omitAgentRuntimeConfig,
  readAgentRuntimeFormValues,
} from "./agentRuntimeConfig";

describe("agentRuntimeConfig", () => {
  it("readAgentRuntimeFormValues parses numeric config keys", () => {
    expect(
      readAgentRuntimeFormValues({
        max_iters: 10,
        max_input_length: "64000",
        temperature: 0.5,
      }),
    ).toEqual({
      max_iters: 10,
      max_input_length: 64000,
      temperature: 0.5,
      top_p: undefined,
      max_tokens: undefined,
      tool_call_run_limit: undefined,
      model_retry_max_retries: undefined,
      model_retry_initial_delay: undefined,
      model_retry_max_delay: undefined,
      tool_retry_max_retries: undefined,
      tool_retry_initial_delay: undefined,
      tool_retry_max_delay: undefined,
      tool_call_limit_enabled: true,
      model_retry_enabled: true,
      tool_retry_enabled: true,
      compaction: {
        enabled: true,
        trigger_fraction: null,
        keep_fraction: null,
        trim_tokens: null,
      },
    });
  });

  it("reads a stored compaction override and can clear it", () => {
    expect(
      readAgentRuntimeFormValues({
        compaction: {
          enabled: false,
          trigger_fraction: 0.7,
          trim_tokens: 4000,
        },
      }).compaction,
    ).toEqual({
      enabled: false,
      trigger_fraction: 0.7,
      keep_fraction: null,
      trim_tokens: 4000,
    });
    expect(
      buildAgentRuntimeRequest(
        {
          compaction: {
            enabled: false,
            trigger_fraction: 0.7,
            keep_fraction: null,
            trim_tokens: null,
          },
        },
        { clearMissing: true },
      ).compaction,
    ).toEqual({
      enabled: false,
      trigger_fraction: 0.7,
      keep_fraction: null,
      trim_tokens: null,
    });
  });

  it("buildAgentRuntimeRequest exposes runtime values as top-level API fields", () => {
    expect(
      buildAgentRuntimeRequest({
        max_iters: 12,
        max_input_length: 32000,
        temperature: undefined,
      }),
    ).toEqual({
      max_iters: 12,
      max_input_length: 32000,
    });
  });

  it("sends a disabled tool retry and clears an enabled switch on edit", () => {
    expect(
      buildAgentRuntimeRequest({
        tool_retry_enabled: false,
        tool_retry_max_retries: 5,
      }),
    ).toEqual({
      tool_retry_enabled: false,
      tool_retry_max_retries: 5,
    });
    expect(
      buildAgentRuntimeRequest(
        { tool_call_limit_enabled: true, model_retry_enabled: true },
        { clearMissing: true },
      ).tool_call_limit_enabled,
    ).toBeNull();
    expect(
      buildAgentRuntimeRequest(
        { tool_retry_enabled: false },
        { clearMissing: true },
      ).tool_retry_enabled,
    ).toBe(false);
  });

  it("omitAgentRuntimeConfig keeps runtime fields out of opaque config", () => {
    expect(
      omitAgentRuntimeConfig({
        max_iters: 12,
        temperature: 0.3,
        plugins: {},
        compaction: { trigger_fraction: 0.7 },
        tool_call_run_limit: 12,
        tool_retry_enabled: false,
      }),
    ).toEqual({ plugins: {} });
  });
});
