import { describe, expect, it } from "vitest";
import type { ProviderModel } from "../../useProviders";
import { pickDefaultModelId } from "./defaultModel";

function model(id: string, enabled = true): ProviderModel {
  return { id, name: id, enabled };
}

describe("pickDefaultModelId (#2312)", () => {
  it("skips a disabled model sitting first in the list", () => {
    expect(
      pickDefaultModelId([
        model("deepseek-flash", false),
        model("deepseek-v4-pro"),
      ]),
    ).toBe("deepseek-v4-pro");
  });

  it("treats a missing enabled flag as enabled", () => {
    const legacy = { id: "legacy", name: "legacy" } as ProviderModel;
    expect(pickDefaultModelId([model("off", false), legacy])).toBe("legacy");
  });

  it("falls back to the first entry when every model is disabled", () => {
    expect(pickDefaultModelId([model("a", false), model("b", false)])).toBe(
      "a",
    );
  });

  it("returns an empty string when the provider has no models", () => {
    expect(pickDefaultModelId(undefined)).toBe("");
    expect(pickDefaultModelId([])).toBe("");
  });
});
