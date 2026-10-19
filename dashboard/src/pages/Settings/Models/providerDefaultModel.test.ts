import { describe, expect, it } from "vitest";
import { providerDefaultModelId } from "./useProviders";

describe("providerDefaultModelId", () => {
  const models = [{ id: "a" }, { id: "b" }];

  it("shows the persisted default when one is set", () => {
    expect(providerDefaultModelId({ default_model: "b", models })).toBe("b");
  });

  it("falls back to the first model when no default was ever saved", () => {
    expect(providerDefaultModelId({ models })).toBe("a");
  });

  it("stays empty after the default was cleared", () => {
    expect(providerDefaultModelId({ default_model: null, models })).toBe("");
    expect(providerDefaultModelId({ default_model: "  ", models })).toBe("");
  });
});
