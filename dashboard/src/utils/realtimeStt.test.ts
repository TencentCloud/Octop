import { afterEach, describe, expect, it, vi } from "vitest";
import { RealtimeSttClient } from "./realtimeStt";

class FakeSocket {
  static instances: FakeSocket[] = [];

  binaryType = "";
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sent: unknown[] = [];
  closed = false;
  readonly url: string;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  send(data: unknown): void {
    this.sent.push(data);
  }

  close(): void {
    this.closed = true;
    this.onclose?.();
  }

  emitMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  emitClose(): void {
    this.onclose?.();
  }

  emitError(): void {
    this.onerror?.();
  }
}

function setup() {
  FakeSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeSocket);
  const handlers = {
    onInterim: vi.fn(),
    onFinal: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
  };
  const client = new RealtimeSttClient(
    "ws://test/api/voice/stt-stream",
    handlers,
  );
  return { client, handlers };
}

function lastSocket(): FakeSocket {
  return FakeSocket.instances[FakeSocket.instances.length - 1];
}

describe("RealtimeSttClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("buffers audio until the server is ready", async () => {
    const { client } = setup();
    const connected = client.connect();
    const socket = lastSocket();

    client.send(new Uint8Array([1, 2]));
    expect(socket.sent).toHaveLength(0);

    socket.emitMessage({ type: "ready" });
    await connected;

    expect(socket.sent).toEqual([new Uint8Array([1, 2])]);
  });

  it("reports the cumulative transcript", async () => {
    const { client, handlers } = setup();
    const connected = client.connect();
    const socket = lastSocket();
    socket.emitMessage({ type: "ready" });
    await connected;

    socket.emitMessage({ type: "interim", text: "你好", sentence_id: 0 });
    expect(handlers.onInterim).toHaveBeenLastCalledWith("你好");

    socket.emitMessage({ type: "final", text: "你好世界", sentence_id: 0 });
    expect(handlers.onFinal).toHaveBeenLastCalledWith("你好世界");

    socket.emitMessage({ type: "interim", text: "再见", sentence_id: 1 });
    expect(handlers.onInterim).toHaveBeenLastCalledWith("你好世界再见");
  });

  it("does not duplicate a sentence confirmed twice", async () => {
    const { client, handlers } = setup();
    const connected = client.connect();
    const socket = lastSocket();
    socket.emitMessage({ type: "ready" });
    await connected;

    socket.emitMessage({ type: "final", text: "你好", sentence_id: 0 });
    socket.emitMessage({ type: "final", text: "你好", sentence_id: 0 });

    expect(handlers.onFinal).toHaveBeenLastCalledWith("你好");
  });

  it("commits a trailing interim sentence when the stream ends", async () => {
    const { client, handlers } = setup();
    const connected = client.connect();
    const socket = lastSocket();
    socket.emitMessage({ type: "ready" });
    await connected;

    socket.emitMessage({ type: "interim", text: "未确认" });
    socket.emitMessage({ type: "done" });

    expect(handlers.onFinal).toHaveBeenLastCalledWith("未确认");
    expect(handlers.onDone).toHaveBeenCalledTimes(1);
    expect(handlers.onError).not.toHaveBeenCalled();
    expect(socket.closed).toBe(true);
  });

  it("sends the end frame through the socket", async () => {
    const { client } = setup();
    const connected = client.connect();
    const socket = lastSocket();
    socket.emitMessage({ type: "ready" });
    await connected;

    client.end();

    expect(JSON.parse(String(socket.sent[socket.sent.length - 1]))).toEqual({
      type: "end",
    });
  });

  it("surfaces the server error message", async () => {
    const { client, handlers } = setup();
    const connected = client.connect();
    const socket = lastSocket();
    socket.emitMessage({ type: "ready" });
    await connected;

    socket.emitMessage({ type: "error", message: "资源包额度已耗尽。" });

    expect(handlers.onError).toHaveBeenCalledWith("资源包额度已耗尽。");
    expect(handlers.onDone).not.toHaveBeenCalled();
  });

  it("reports an unexpected close as a transport failure", async () => {
    const { client, handlers } = setup();
    const connected = client.connect();
    const socket = lastSocket();
    socket.emitMessage({ type: "ready" });
    await connected;

    socket.emitClose();

    expect(handlers.onError).toHaveBeenCalledWith(null);
  });

  it("rejects connect when the socket fails before ready", async () => {
    const { client } = setup();
    const connected = client.connect();
    lastSocket().emitError();

    await expect(connected).rejects.toThrow();
  });

  it("stops sending once closed", async () => {
    const { client } = setup();
    const connected = client.connect();
    const socket = lastSocket();
    socket.emitMessage({ type: "ready" });
    await connected;

    client.close();
    client.send(new Uint8Array([1]));

    expect(socket.sent).toHaveLength(0);
  });
});
