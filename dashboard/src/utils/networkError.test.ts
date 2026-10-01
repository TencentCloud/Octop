import { afterEach, describe, expect, it, vi } from "vitest";
import { isNetworkFetchError } from "./networkError";

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
