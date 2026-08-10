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

  it("omitAgentRuntimeConfig keeps runtime fields out of opaque config", () => {
    expect(
      omitAgentRuntimeConfig({
        max_iters: 12,
        temperature: 0.3,
        plugins: {},
      }),
    ).toEqual({ plugins: {} });
  });
});
