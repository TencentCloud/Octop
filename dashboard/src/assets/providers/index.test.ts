import { describe, expect, it } from "vitest";
import yuanbaoIcon from "../channels/yuanbao.svg";
import { getProviderLogo } from "./index";

describe("getProviderLogo", () => {
  it("uses the Yuanbao product mark shared with the channel", () => {
    expect(getProviderLogo("yuanbao")).toBe(yuanbaoIcon);
    expect(getProviderLogo("yuanbao-search")).toBe(yuanbaoIcon);
  });
});
