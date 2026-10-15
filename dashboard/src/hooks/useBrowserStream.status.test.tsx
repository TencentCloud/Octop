import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import BrowserViewer from "../components/BrowserViewer";
import { useBrowserStream } from "./useBrowserStream";

vi.mock("../api/request", () => ({ getAuthToken: () => null }));

class FakeWebSocket {
  static OPEN = 1;
  static CLOSING = 2;
  static current: FakeWebSocket;
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();

  constructor() {
    FakeWebSocket.current = this;
  }

  status(status: string) {
    this.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ type: "status", status }),
      }),
    );
  }
}

function StreamView({ reconnect }: { reconnect: () => void }) {
  const stream = useBrowserStream();
  return (
    <>
      <button
        onClick={() => stream.connect("", 1280, 800, { onFrame: () => {} })}
      >
        Connect
      </button>
      <BrowserViewer
        status={stream.status}
        tabs={stream.tabs}
        switchTab={stream.switchTab}
        closeTab={stream.closeTab}
        newTab={stream.newTab}
        sendEvent={stream.sendEvent}
        navUrl=""
        onNavUrlChange={() => {}}
        onNavigate={stream.navigate}
        interactive={false}
        onReconnect={reconnect}
      />
    </>
  );
}

describe("browser capture status messages", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the existing failure UI and recovers on the same connection", () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const reconnect = vi.fn();
    const { container } = render(<StreamView reconnect={reconnect} />);
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    const socket = FakeWebSocket.current;

    act(() => socket.status("streaming"));
    expect(container.querySelector("canvas")).toBeInTheDocument();

    act(() => socket.status("error"));
    expect(screen.getByText("browserViewer.connectFailed")).toBeInTheDocument();
    expect(container.querySelector("canvas")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "browserViewer.reconnect" }),
    );
    expect(reconnect).toHaveBeenCalledOnce();

    act(() => socket.status("streaming"));
    expect(
      screen.queryByText("browserViewer.connectFailed"),
    ).not.toBeInTheDocument();
    expect(container.querySelector("canvas")).toBeInTheDocument();
    expect(FakeWebSocket.current).toBe(socket);
  });
});
