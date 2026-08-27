import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../../api/request", () => ({ request }));

import { wizardApi, type WizardProviderModel } from "./wizardClient";

describe("setup provider probes", () => {
  beforeEach(() => {
    request.mockReset();
    request.mockResolvedValue({ ok: true });
  });

  it("sends the selected model metadata with the legacy model id", async () => {
    const model: WizardProviderModel = {
      id: "grok-4.6",
      name: "Grok 4.6",
      enabled: true,
      input: ["text", "image"],
      thinking: null,
      reasoning: true,
      max_input_tokens: 2_000_000,
      context_window: 2_000_000,
      max_output_tokens: 131_072,
      wire_api: "openai_responses",
      endpoint_base_url: "https://opencode.ai/zen/go/v1",
      native_tool_search: true,
      reasoning_config: {
        supported: true,
        toggle: true,
        default_mode: "auto",
        efforts: ["low", "high"],
        default_effort: "high",
        effort_type: "enum",
        adapter: "openai_reasoning_effort",
      },
    };

    await wizardApi.testProvider(
      {
        name: "OpenCode Go",
        type: "openai",
        api_key: "secret",
        base_url: "https://opencode.ai/zen/go/v1",
        model_id: model.id,
        model,
      },
      "wizard-token",
    );

    expect(request).toHaveBeenCalledWith("/setup/test-provider", {
      method: "POST",
      body: JSON.stringify({
        name: "OpenCode Go",
        type: "openai",
        api_key: "secret",
        base_url: "https://opencode.ai/zen/go/v1",
        model_id: "grok-4.6",
        model,
      }),
      headers: { Authorization: "Bearer wizard-token" },
    });
  });
});
