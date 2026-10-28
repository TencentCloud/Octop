import { afterEach, describe, expect, test, vi } from "vitest";

/**
 * The shell serves the Dashboard from a custom scheme that cannot carry a
 * WebSocket handshake, so it hands the page a loopback relay instead (§5.2).
 * These cover both modes: with the bridge, and without it (a browser tab or a
 * server deployment), where the address must stay derived from the page origin.
 */

async function loadModule(bridge: unknown) {
  vi.resetModules();
  if (bridge === undefined) {
    delete (window as unknown as Record<string, unknown>).octopDesktop;
  } else {
    (window as unknown as Record<string, unknown>).octopDesktop = bridge;
  }
  return import("./desktopWsUrl");
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).octopDesktop;
});

describe("resolveWsUrl", () => {
  test("falls back to the page origin in a browser", async () => {
    const { resolveWsUrl } = await loadModule(undefined);
    expect(resolveWsUrl("/api/mobile-stream/ws")).toBe(
      `ws://${window.location.host}/api/mobile-stream/ws`,
    );
  });

  test("dials the shell's relay when the bridge has one", async () => {
    const { resolveWsUrl } = await loadModule({
      wsEndpoint: () => ({ baseUrl: "ws://127.0.0.1:51234/relay-token", token: "relay-token" }),
    });
    // The token is a path segment so callers can still append their own query.
    expect(`${resolveWsUrl("/api/terminal/ws")}?session_id=s1`).toBe(
      "ws://127.0.0.1:51234/relay-token/api/terminal/ws?session_id=s1",
    );
  });

  test("falls back when the shell could not bind the relay", async () => {
    const { resolveWsUrl } = await loadModule({ wsEndpoint: () => null });
    expect(resolveWsUrl("/api/desktop-stream/ws")).toBe(
      `ws://${window.location.host}/api/desktop-stream/ws`,
    );
  });

  test("falls back on a shell that predates the relay", async () => {
    const { desktopWsBase, resolveWsUrl } = await loadModule({});
    expect(desktopWsBase()).toBeNull();
    expect(resolveWsUrl("/api/browser-stream/ws")).toBe(
      `ws://${window.location.host}/api/browser-stream/ws`,
    );
  });

  test("reads the endpoint once per launch", async () => {
    const wsEndpoint = vi.fn(() => ({ baseUrl: "ws://127.0.0.1:1/t", token: "t" }));
    const { resolveWsUrl } = await loadModule({ wsEndpoint });
    resolveWsUrl("/api/a");
    resolveWsUrl("/api/b");
    expect(wsEndpoint).toHaveBeenCalledTimes(1);
  });
});
