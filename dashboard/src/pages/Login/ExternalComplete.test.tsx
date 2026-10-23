import { describe, expect, it } from "vitest";
import { readExternalCompleteParams } from "./ExternalComplete";

describe("readExternalCompleteParams", () => {
  it("prefers hash over query", () => {
    expect(
      readExternalCompleteParams(
        "#access_token=from-hash&redirect=%2Fsettings",
        "?access_token=from-query",
      ),
    ).toEqual({ accessToken: "from-hash", redirect: "/settings" });
  });

  it("falls back to query for legacy links", () => {
    expect(
      readExternalCompleteParams("", "?access_token=legacy&redirect=%2Fchat"),
    ).toEqual({ accessToken: "legacy", redirect: "/chat" });
  });

  it("returns a null token when neither hash nor query carries one", () => {
    expect(readExternalCompleteParams("#redirect=%2Fchat", "")).toEqual({
      accessToken: null,
      redirect: "/chat",
    });
  });

  it("returns redirect verbatim and leaves validation to safeRedirect", () => {
    expect(
      readExternalCompleteParams(
        "#access_token=t&redirect=%2F%2Fidentity.example.com",
        "",
      ),
    ).toEqual({ accessToken: "t", redirect: "//identity.example.com" });
  });
});
