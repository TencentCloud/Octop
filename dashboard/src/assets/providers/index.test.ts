import { describe, expect, it } from "vitest";
import yuanbaoIcon from "../channels/yuanbao.svg";
import { getProviderDocs, getProviderLogo } from "./index";

describe("getProviderLogo", () => {
  it("uses the Yuanbao product mark shared with the channel", () => {
    expect(getProviderLogo("yuanbao")).toBe(yuanbaoIcon);
    expect(getProviderLogo("yuanbao-search")).toBe(yuanbaoIcon);
  });
});

describe("LLMTR preset assets", () => {
  it("has docs and no built-in logo", () => {
    expect(getProviderDocs("llmtr")).toBe("https://llmtr.com");
    expect(getProviderLogo("llmtr")).toBeUndefined();
  });
});

