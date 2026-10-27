import { describe, expect, it } from "vitest";
import { toProviderModelPayload } from "./CustomProviderModal";
import type { ProviderModel } from "../../useProviders";

const reasoningConfig: NonNullable<ProviderModel["reasoning_config"]> = {
  supported: true,
  toggle: true,
  default_mode: "auto",
  efforts: ["medium", "xhigh"],
  default_effort: "medium",
  effort_type: "enum",
  adapter: "dashscope",
};

describe("toProviderModelPayload", () => {
  it("keeps reasoning_config instead of dropping it", () => {
    const models: ProviderModel[] = [
      {
        id: "alzheimer",
        name: "Alzheimer",
        enabled: true,
        input: ["text", "image"],
        reasoning: true,
        reasoning_config: reasoningConfig,
        context_window: 128000,
        max_tokens: 8000,
      },
    ];

    const [entry] = toProviderModelPayload(models, false);

    expect(entry.reasoning_config).toEqual(reasoningConfig);
    expect(entry.reasoning).toBe(true);
    expect(entry.context_window).toBe(128000);
    expect(entry.max_tokens).toBe(8000);
  });

  it("keeps api_mode / api_fallback / visibility fields from the editor", () => {
    const models: ProviderModel[] = [
      {
        id: "qwen",
        name: "Qwen",
        enabled: true,
        api_mode: "responses",
        api_fallback: "chat_completions",
        visibility: "groups",
        group_ids: ["g1"],
      },
    ];

    const [entry] = toProviderModelPayload(models, false);

    expect(entry.api_mode).toBe("responses");
    expect(entry.api_fallback).toBe("chat_completions");
    expect(entry.visibility).toBe("groups");
    expect(entry.group_ids).toEqual(["g1"]);
  });

  it("defaults input to text and keeps thinking null when unset", () => {
    const [entry] = toProviderModelPayload(
      [{ id: "m", name: "m", enabled: true }],
      false,
    );

    expect(entry.input).toEqual(["text"]);
    expect(entry.thinking).toBeNull();
    expect(entry.embedding).toBeUndefined();
  });

  it("marks models as embedding in the embedding lane", () => {
    const [entry] = toProviderModelPayload(
      [{ id: "bge-m3", name: "bge-m3", enabled: true }],
      true,
    );

    expect(entry.embedding).toBe(true);
    expect(entry.task).toBe("embedding");
  });
});
