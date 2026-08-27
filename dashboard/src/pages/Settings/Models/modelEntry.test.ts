import { describe, expect, it } from "vitest";
import { buildProviderModelEntry } from "./modelEntry";
import type { ProviderModel } from "./useProviders";

describe("buildProviderModelEntry", () => {
  it("preserves opaque provider metadata while updating visible fields", () => {
    const existing: ProviderModel & {
      provider_extension: Record<string, unknown>;
    } = {
      id: "grok-4.6",
      name: "Grok 4.6",
      enabled: false,
      input: ["text"],
      thinking: true,
      context_window: 1_000_000,
      max_tokens: 65_536,
      max_input_tokens: 1_000_000,
      wire_api: "openai_responses",
      endpoint_base_url: "https://opencode.ai/zen/go/v1",
      native_tool_search: true,
      options: { thinking: { type: "enabled", budget_tokens: 8192 } },
      provider_extension: { cache_control: "ephemeral" },
    };

    const updated = buildProviderModelEntry(
      {
        id: "grok-4.6",
        name: "Grok 4.6 (reviewed)",
        input: ["text", "image"],
        context_window: 2_000_000,
        max_tokens: 131_072,
        reasoning: false,
        embedding: false,
      },
      { existing, isOnnx: false },
    );

    expect(updated).toEqual(
      expect.objectContaining({
        name: "Grok 4.6 (reviewed)",
        enabled: false,
        input: ["text", "image"],
        thinking: true,
        context_window: 2_000_000,
        max_tokens: 131_072,
        max_input_tokens: 1_000_000,
        wire_api: "openai_responses",
        endpoint_base_url: "https://opencode.ai/zen/go/v1",
        native_tool_search: true,
        options: { thinking: { type: "enabled", budget_tokens: 8192 } },
        provider_extension: { cache_control: "ephemeral" },
      }),
    );
  });
});
