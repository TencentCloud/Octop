import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../../../api/request", () => ({ request }));

import { testProviderDraft, toProviderProbeModel } from "./providerApi";

describe("provider draft probes", () => {
  beforeEach(() => {
    request.mockReset();
    request.mockResolvedValue({ ok: true });
  });

  it("sends complete model routing metadata and maps max_tokens", async () => {
    const model = toProviderProbeModel({
      id: "qwen3.7-max",
      name: "Qwen3.7 Max",
      enabled: true,
      input: ["text", "image"],
      max_input_tokens: 1_000_000,
      context_window: 1_000_000,
      max_tokens: 65_536,
      reasoning: true,
      reasoning_config: {
        supported: true,
        toggle: true,
        default_mode: "auto",
        efforts: ["low", "high"],
        default_effort: "high",
        effort_type: "enum",
        adapter: "anthropic_adaptive",
      },
      wire_api: "anthropic_messages",
      endpoint_base_url: "https://opencode.ai/zen/go",
      native_tool_search: true,
      options: { thinking: { type: "adaptive" } },
    });

    await testProviderDraft({
      name: "OpenCode Go",
      kind: "openai",
      api_key: "secret",
      base_url: "https://opencode.ai/zen/go/v1",
      model_id: model.id,
      model,
    });

    expect(model).not.toHaveProperty("max_tokens");
    expect(model.max_output_tokens).toBe(65_536);
    expect(model.native_tool_search).toBe(true);
    expect(request).toHaveBeenCalledWith("/admin/providers/test-draft", {
      method: "POST",
      body: JSON.stringify({
        name: "OpenCode Go",
        kind: "openai",
        api_key: "secret",
        base_url: "https://opencode.ai/zen/go/v1",
        model_id: "qwen3.7-max",
        model,
        extra_json: null,
        embedding: false,
      }),
    });
  });
});
