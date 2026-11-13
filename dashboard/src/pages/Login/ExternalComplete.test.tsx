import { describe, expect, it } from "vitest";
import { readExternalCompleteParams } from "./ExternalComplete";

describe("readExternalCompleteParams", () => {
  it("reads the one-time code from the hash only", () => {
    expect(
      readExternalCompleteParams(
        "#code=from-hash&redirect=%2Fsettings",
        "?code=from-query",
      ),
    ).toEqual({ code: "from-hash", redirect: "/settings" });
  });

  it("does not accept a query code as the credential", () => {
    expect(
      readExternalCompleteParams("", "?code=legacy&redirect=%2Fchat"),
    ).toEqual({ code: null, redirect: "/chat" });
  });

  it("returns a null code when the hash does not carry one", () => {
    expect(readExternalCompleteParams("#redirect=%2Fchat", "")).toEqual({
      code: null,
      redirect: "/chat",
    });
  });

  it("still reads redirect from the query when the hash has only a code", () => {
    expect(
      readExternalCompleteParams("#code=once", "?redirect=%2Fagents"),
    ).toEqual({ code: "once", redirect: "/agents" });
  });

  it("returns redirect verbatim and leaves validation to safeRedirect", () => {
    expect(
      readExternalCompleteParams(
        "#code=t&redirect=%2F%2Fidentity.example.com",
        "",
      ),
    ).toEqual({ code: "t", redirect: "//identity.example.com" });
  });

  it("ignores access_token in the hash and the query", () => {
    expect(
      readExternalCompleteParams(
        "#access_token=jwt",
        "?access_token=jwt&redirect=%2Fchat",
      ),
    ).toEqual({ code: null, redirect: "/chat" });
  });
});
