import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatMessageQueueProvider } from "./ChatMessageQueueContext";
import {
  useChatMessageQueue,
  type ChatQueueFlushHandler,
} from "./useChatMessageQueue";

const stream = vi.hoisted(() => ({
  listeners: new Set<
    (event: { kind: "streamEnd"; sessionId: string }) => void
  >(),
}));
vi.mock("./chatStore", () => ({
  onStreamEvent: (
    listener: (event: { kind: "streamEnd"; sessionId: string }) => void,
  ) => {
    stream.listeners.add(listener);
    return () => stream.listeners.delete(listener);
  },
}));

function Composer({
  onFlush,
  streaming = true,
  blocked = false,
}: {
  onFlush: ChatQueueFlushHandler;
  streaming?: boolean;
  blocked?: boolean;
}) {
  const queue = useChatMessageQueue({
    agentId: "agent-a",
    threadId: "thread-a",
    isStreaming: streaming,
    onFlush,
    shouldDeferFlush: () => blocked,
    isThreadStreaming: () => false,
  });
  return (
    <>
      <button
        onClick={() =>
          queue.enqueue({
            text: "Queued task",
            attachments: [
              {
                path: "inbound/test.txt",
                name: "test.txt",
                mimeType: "text/plain",
              },
            ],
            modelRef: "provider/model",
          })
        }
      >
        Enqueue
      </button>
      <output>{queue.items.length}</output>
    </>
  );
}
const end = () =>
  stream.listeners.forEach((listener) =>
    listener({ kind: "streamEnd", sessionId: "thread-a" }),
  );

describe("workspace chat queue lifetime", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    stream.listeners.clear();
  });
  it("sends to the original agent/thread after leaving the chat page", () => {
    const onFlush = vi.fn();
    const { rerender } = render(
      <ChatMessageQueueProvider>
        <Composer onFlush={onFlush} />
      </ChatMessageQueueProvider>,
    );
    act(() => screen.getByRole("button", { name: "Enqueue" }).click());
    rerender(
      <ChatMessageQueueProvider>
        <p>Automation page</p>
      </ChatMessageQueueProvider>,
    );
    expect(stream.listeners.size).toBe(1);
    act(() => {
      end();
      vi.runAllTimers();
    });
    expect(onFlush).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        text: "Queued task",
        modelRef: "provider/model",
        attachments: expect.arrayContaining([
          expect.objectContaining({ path: "inbound/test.txt" }),
        ]),
      }),
      {
        agentId: "agent-a",
        threadId: "thread-a",
        queueKey: "agent-a:thread-a",
      },
    );
    rerender(
      <ChatMessageQueueProvider>
        <Composer onFlush={onFlush} streaming={false} />
      </ChatMessageQueueProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("0");
  });
  it("retains a queue across page changes while an approval is pending", () => {
    const onFlush = vi.fn();
    const { rerender } = render(
      <ChatMessageQueueProvider>
        <Composer onFlush={onFlush} blocked />
      </ChatMessageQueueProvider>,
    );
    act(() => screen.getByRole("button", { name: "Enqueue" }).click());
    rerender(
      <ChatMessageQueueProvider>
        <p>Other page</p>
      </ChatMessageQueueProvider>,
    );
    act(() => {
      end();
      vi.runAllTimers();
    });
    expect(onFlush).not.toHaveBeenCalled();
    rerender(
      <ChatMessageQueueProvider>
        <Composer onFlush={onFlush} streaming={false} />
      </ChatMessageQueueProvider>,
    );
    act(() => vi.runAllTimers());
    expect(onFlush).toHaveBeenCalledOnce();
  });
  it("cancels scheduled sends and drops the queue when the authenticated workspace unmounts", () => {
    const onFlush = vi.fn();
    const { rerender, unmount } = render(
      <ChatMessageQueueProvider>
        <Composer onFlush={onFlush} />
      </ChatMessageQueueProvider>,
    );
    act(() => screen.getByRole("button", { name: "Enqueue" }).click());
    rerender(
      <ChatMessageQueueProvider>
        <p>Other page</p>
      </ChatMessageQueueProvider>,
    );
    act(() => end());
    unmount();
    act(() => vi.runAllTimers());
    expect(onFlush).not.toHaveBeenCalled();
    expect(stream.listeners.size).toBe(0);
    render(
      <ChatMessageQueueProvider>
        <Composer onFlush={onFlush} />
      </ChatMessageQueueProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("0");
  });
  it("replaces the background dispatcher without sending a queue item twice", () => {
    const oldFlush = vi.fn(),
      nextFlush = vi.fn();
    const { rerender } = render(
      <ChatMessageQueueProvider>
        <Composer onFlush={oldFlush} />
      </ChatMessageQueueProvider>,
    );
    act(() => screen.getByRole("button", { name: "Enqueue" }).click());
    rerender(
      <ChatMessageQueueProvider>
        <p>Other page</p>
      </ChatMessageQueueProvider>,
    );
    act(() => end());
    rerender(
      <ChatMessageQueueProvider>
        <Composer onFlush={nextFlush} streaming={false} />
      </ChatMessageQueueProvider>,
    );
    act(() => vi.runAllTimers());
    expect(oldFlush).not.toHaveBeenCalled();
    expect(nextFlush).toHaveBeenCalledOnce();
    expect(stream.listeners.size).toBe(1);
  });
});
