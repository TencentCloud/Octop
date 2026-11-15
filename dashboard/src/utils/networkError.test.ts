import { afterEach, describe, expect, it, vi } from "vitest";
import { isCatalogNetworkError, isNetworkFetchError } from "./networkError";

describe("isNetworkFetchError", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("detects navigator.offline", () => {
    vi.stubGlobal("navigator", { onLine: false });
    expect(isNetworkFetchError(new Error("anything"))).toBe(true);
  });

  it("detects Failed to fetch", () => {
    vi.stubGlobal("navigator", { onLine: true });
    expect(isNetworkFetchError(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("ignores HTTP API errors", () => {
    vi.stubGlobal("navigator", { onLine: true });
    expect(
      isNetworkFetchError(new Error("Request failed with status 503")),
    ).toBe(false);
  });
});

describe("isCatalogNetworkError", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("treats a catalog network code as a network problem", () => {
    vi.stubGlobal("navigator", { onLine: true });
    const error = new Error(
      '502 - {"error":{"code":"NETWORK_ERROR","message":"network"}}',
    );
    expect(isCatalogNetworkError(error, "NETWORK_ERROR")).toBe(true);
  });

  it("leaves a marketplace outage as a market problem", () => {
    vi.stubGlobal("navigator", { onLine: true });
    const error = new Error(
      '502 - {"error":{"code":"PLUGIN_MARKET_FAILED","message":"down"}}',
    );
    expect(isCatalogNetworkError(error, "NETWORK_ERROR")).toBe(false);
  });
});
