import { describe, expect, it } from "vitest";

import { oauthCallbackSupported } from "./oauthCallback";

describe("oauthCallbackSupported", () => {
  it("allows HTTPS and loopback HTTP", () => {
    expect(oauthCallbackSupported("https://octop.example/connectors")).toBe(
      true,
    );
    expect(oauthCallbackSupported("http://localhost:8088/")).toBe(true);
    expect(oauthCallbackSupported("http://127.0.0.1:8088/")).toBe(true);
    expect(oauthCallbackSupported("http://[::1]:8088/")).toBe(true);
  });

  it("rejects public HTTP (no OAuth callback)", () => {
    expect(oauthCallbackSupported("http://192.168.1.10:8088/")).toBe(false);
    expect(oauthCallbackSupported("http://octop.example/")).toBe(false);
  });
});
