import { afterEach, describe, expect, it, vi } from "vitest";
import { removeSession, sendTurn } from "./chatStore";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = 1;
      this.onopen?.();
    });
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}

afterEach(() => {
  removeSession("team-model-test");
  vi.unstubAllGlobals();
  FakeWebSocket.instances = [];
});

describe("team model websocket payload", () => {
  it.each([
    [true, "p/chosen", true],
    [false, "p/chosen", false],
    [true, null, false],
  ] as const)(
    "sends an override only for a selected model (%s, %s)",
    async (enabled, model, expected) => {
      vi.stubGlobal("WebSocket", FakeWebSocket);
      const pending = sendTurn(
        "team-model-test",
        "hi",
        "host",
        "",
        undefined,
        undefined,
        model,
        "team-model-test",
        [],
        [],
        [],
        undefined,
        undefined,
        "craft",
        undefined,
        enabled,
      );
      await Promise.resolve();
      const ws = FakeWebSocket.instances[0];
      const frame = JSON.parse(ws.sent[0]);
      expect(frame.apply_model_to_team ?? false).toBe(expected);
      expect(frame.model ?? null).toBe(model);
      ws.close();
      await pending;
    },
  );
});
