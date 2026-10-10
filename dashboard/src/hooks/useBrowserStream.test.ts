import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useBrowserStream } from "./useBrowserStream";

type StreamCallbacks = Parameters<
  ReturnType<typeof useBrowserStream>["connect"]
>[3];

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  readonly sentMessages: string[] = [];
  readonly close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
  });
  readonly send = vi.fn((data: string) => {
    this.sentMessages.push(data);
  });

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  emitOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  emitMessage(message: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  }

  emitError() {
    this.onerror?.(new Event("error"));
  }

  emitClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }
}

function callbacks(): StreamCallbacks {
  return {
    onFrame: vi.fn(),
    onStatusChange: vi.fn(),
    onError: vi.fn(),
  };
}

describe("useBrowserStream connection generations", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("ignores lifecycle events from an old socket after reconnect", () => {
    const callbacksA = callbacks();
    const callbacksB = callbacks();
    const { result } = renderHook(() => useBrowserStream());

    act(() => {
      result.current.connect("https://first.example", 800, 600, callbacksA);
    });
    const socketA = MockWebSocket.instances[0]!;

    act(() => {
      result.current.connect("https://second.example", 1024, 768, callbacksB);
    });
    const socketB = MockWebSocket.instances[1]!;

    // A can finish opening after B has replaced it, but must not send a stale
    // start message or change the URL shown for the active connection.
    act(() => socketA.emitOpen());
    expect(socketA.sentMessages).toEqual([]);
    expect(result.current.currentUrl).toBe("");

    act(() => {
      socketA.emitError();
      socketA.emitClose();
    });
    expect(result.current.status).toBe("connecting");

    act(() => socketB.emitOpen());
    expect(result.current.currentUrl).toBe("https://second.example");

    act(() => socketB.emitMessage({ type: "status", status: "streaming" }));
    expect(result.current.status).toBe("streaming");

    // These callbacks belong to A and must not stop or fail B.
    act(() => {
      socketA.emitError();
      socketA.emitClose();
    });

    expect(result.current.status).toBe("streaming");
    expect(callbacksB.onError).not.toHaveBeenCalled();
  });

  it("does not let an old socket message update the active stream", () => {
    const callbacksA = callbacks();
    const callbacksB = callbacks();
    const { result } = renderHook(() => useBrowserStream());

    act(() => {
      result.current.connect("https://first.example", 800, 600, callbacksA);
      result.current.connect("https://second.example", 1024, 768, callbacksB);
    });
    const socketA = MockWebSocket.instances[0]!;
    const socketB = MockWebSocket.instances[1]!;
    const activeTab = {
      id: "active",
      url: "https://second.example",
      title: "Active tab",
      active: true,
    };

    act(() => {
      socketB.emitMessage({ type: "status", status: "streaming" });
      socketB.emitMessage({ type: "tabs", tabs: [activeTab] });
    });
    expect(result.current.status).toBe("streaming");
    expect(result.current.tabs).toEqual([activeTab]);

    act(() => {
      socketA.emitMessage({ type: "frame", data: "stale-frame" });
      socketA.emitMessage({ type: "status", status: "error" });
      socketA.emitMessage({
        type: "tabs",
        tabs: [
          {
            id: "stale",
            url: "https://first.example",
            title: "Stale tab",
            active: true,
          },
        ],
      });
    });

    expect(callbacksB.onFrame).not.toHaveBeenCalled();
    expect(result.current.status).toBe("streaming");
    expect(result.current.tabs).toEqual([activeTab]);
  });

  it("keeps a disconnected stream idle when the old socket emits later", () => {
    const streamCallbacks = callbacks();
    const { result } = renderHook(() => useBrowserStream());

    act(() => {
      result.current.connect("https://first.example", 800, 600, streamCallbacks);
    });
    const socket = MockWebSocket.instances[0]!;

    act(() => result.current.disconnect());
    expect(result.current.status).toBe("idle");

    act(() => {
      socket.emitError();
      socket.emitClose();
      socket.emitMessage({ type: "frame", data: "late-frame" });
    });

    expect(result.current.status).toBe("idle");
    expect(streamCallbacks.onFrame).not.toHaveBeenCalled();
  });
});
