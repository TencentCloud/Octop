import { describe, expect, it } from "vitest";
import { modelNameLabel, modelRefLabel } from "./modelOptions";

describe("modelRefLabel", () => {
  it("uses the picker label so two vendors of the same model stay distinct", () => {
    const models = [
      { provider_name: "Huawei", model: "deepseek-v3", name: "DeepSeek V3" },
      { provider_name: "Tencent", model: "deepseek-v3", name: "DeepSeek V3" },
    ];
    expect(modelRefLabel("Huawei/deepseek-v3", models)).toBe(
      "Huawei / DeepSeek V3",
    );
    expect(modelRefLabel("Tencent/deepseek-v3", models)).toBe(
      "Tencent / DeepSeek V3",
    );
  });

  it("keeps the provider when the catalog entry is missing", () => {
    expect(modelRefLabel("Huawei/deepseek-v3")).toBe("Huawei / deepseek-v3");
  });
});

describe("modelNameLabel", () => {
  it("drops the provider for the composer chip", () => {
    const models = [
      { provider_name: "Huawei", model: "deepseek-v3", name: "DeepSeek V3" },
    ];
    expect(modelNameLabel("Huawei/deepseek-v3", models)).toBe("DeepSeek V3");
    expect(modelNameLabel("Huawei/deepseek-v3")).toBe("deepseek-v3");
  });
});
