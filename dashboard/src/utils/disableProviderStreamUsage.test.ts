import { describe, expect, it } from "vitest";
import type { ResolvedModel } from "../api/types";
import {
  providerIdForModelRef,
  providerIdForTurn,
} from "./disableProviderStreamUsage";

const models: ResolvedModel[] = [
  {
    provider_id: 2,
    provider_name: "mindie",
    provider_kind: "openai",
    model: "qwen",
    name: "Qwen",
  },
  {
    provider_id: 7,
    provider_name: "openai",
    provider_kind: "openai",
    model: "gpt-4o",
    name: "GPT-4o",
  },
];

describe("providerIdForModelRef", () => {
  it("matches the composer model ref", () => {
    expect(providerIdForModelRef(models, "openai/gpt-4o")).toBe(7);
  });

  it("does not guess the first catalog model when Auto", () => {
    expect(providerIdForModelRef(models, null)).toBeNull();
    expect(providerIdForModelRef(models, "")).toBeNull();
    expect(providerIdForModelRef(models, "auto")).toBeNull();
  });

  it("returns null when the ref is not in the catalog", () => {
    expect(providerIdForModelRef(models, "other/missing")).toBeNull();
  });
});

describe("providerIdForTurn", () => {
  it("uses the first explicit ref that matches", () => {
    expect(
      providerIdForTurn(models, [null, "auto", "openai/gpt-4o", "mindie/qwen"]),
    ).toBe(7);
  });

  it("prefers this-turn composer over agent / global defaults", () => {
    expect(
      providerIdForTurn(models, [
        "mindie/qwen",
        "openai/gpt-4o",
        "openai/gpt-4o",
      ]),
    ).toBe(2);
  });

  it("returns null when Auto cannot be resolved", () => {
    expect(providerIdForTurn(models, [null, "", "auto"])).toBeNull();
  });
});
