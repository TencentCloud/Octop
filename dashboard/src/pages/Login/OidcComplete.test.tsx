import { describe, expect, it } from "vitest";
import { readOidcCompleteParams, safeRedirect } from "./OidcComplete";

describe("safeRedirect", () => {
  it.each([
    ["//identity.example.com", "/chat"],
    ["http://identity.example.com", "/chat"],
    ["/chat://identity.example.com", "/chat"],
    ["/chat\\identity.example.com", "/chat"],
    ["chat", "/chat"],
    ["/\n/identity.example.com", "/chat"],
    ["/\t/identity.example.com", "/chat"],
    ["/\r/identity.example.com", "/chat"],
    ["/embed/chat/agent-a\u007f", "/chat"],
    ["/embed/chat/agent-a\u0000", "/chat"],
    ["/login", "/chat"],
    ["/login?redirect=/embed/chat/agent-a", "/chat"],
    ["/login/#retry", "/chat"],
    ["/login/oidc/complete", "/login/oidc/complete"],
    ["/embed/chat/agent-a", "/embed/chat/agent-a"],
    ["/agents", "/agents"],
  ])("allows only internal paths: %s", (redirect, expected) => {
    expect(safeRedirect(redirect)).toBe(expected);
  });
});

describe("readOidcCompleteParams", () => {
  it("prefers hash over query", () => {
    expect(
      readOidcCompleteParams(
        "#code=from-hash&redirect=%2Fsettings",
        "?code=from-query",
      ),
    ).toEqual({ code: "from-hash", redirect: "/settings", bind: false });
  });

  it("falls back to query for legacy links", () => {
    expect(readOidcCompleteParams("", "?code=legacy&redirect=%2Fchat")).toEqual(
      {
        code: "legacy",
        redirect: "/chat",
        bind: false,
      },
    );
  });
});
