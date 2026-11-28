import { describe, expect, it } from "vitest";
import { inferInputModalities } from "./wizardModelMeta";

describe("inferInputModalities", () => {
  it("respects explicit non-empty input without re-adding image from name hints", () => {
    expect(inferInputModalities("glm-5-w8a8-vllm-Bige", ["text"])).toEqual([
      "text",
    ]);
    expect(inferInputModalities("qwen2.5-vl", ["text"])).toEqual(["text"]);
    expect(inferInputModalities("gpt-4o", ["text"])).toEqual(["text"]);
    expect(inferInputModalities("custom", ["text", "image"])).toEqual([
      "text",
      "image",
    ]);
  });

  it("infers vision from known naming conventions when input is omitted or empty", () => {
    expect(inferInputModalities("qwen2.5-vl")).toEqual(["text", "image"]);
    expect(inferInputModalities("qwen-vl-max", [])).toEqual(["text", "image"]);
    expect(inferInputModalities("qwen3-vl2")).toEqual(["text", "image"]);
    expect(inferInputModalities("gpt-4o-mini")).toEqual(["text", "image"]);
  });

  it("does not treat -vllm as a -vl vision suffix", () => {
    expect(inferInputModalities("glm-5-w8a8-vllm-Bige")).toEqual(["text"]);
  });
});
