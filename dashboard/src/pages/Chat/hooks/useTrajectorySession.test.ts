import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TrajectoryEvent } from "../../../api/modules/trajectory";
import { useTrajectorySession } from "./useTrajectorySession";

const historyMock = vi.fn();
const streamUrlMock = vi.fn(
  (_agentId: string, _threadId: string, afterSeq?: number) =>
    `http://trajectory.test/stream?after_seq=${afterSeq ?? ""}`,
);

vi.mock("../../../api/modules/trajectory", () => ({
  trajectoryApi: {
    history: (...args: unknown[]) => historyMock(...args),
    streamUrl: (agentId: string, threadId: string, afterSeq?: number): string =>
      streamUrlMock(agentId, threadId, afterSeq),
  },
}));

type Listener = (event: MessageEvent) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  close = vi.fn();
  private listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener): void {
    const set = this.listeners.get(type) ?? new Set<Listener>();
    set.add(listener as Listener);
    this.listeners.set(type, set);
  }

  removeEventListener(type: string, listener: EventListener): void {
    this.listeners.get(type)?.delete(listener as Listener);
  }

  emit(type: string, data: unknown): void {
    const event = { data: JSON.stringify(data) } as MessageEvent;
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }
}

function event(
  overrides: Partial<TrajectoryEvent> &
    Pick<TrajectoryEvent, "event_id" | "kind">,
): TrajectoryEvent {
  return {
    thread_id: "T1",
    agent_id: "A1",
    seq: 1,
    ts: 1,
    turn_id: null,
    request_seq: null,
    is_error: false,
    summary: "",
    payload: {},
    ...overrides,
  };
}

const toolEvent = event({
  event_id: "tool-1",
  kind: "tool",
  seq: 1,
  payload: { name: "read_file" },
});

const assistantEvent = event({
  event_id: "asst-1",
  kind: "assistant",
  seq: 2,
  request_seq: 1,
  summary: "ok",
});

describe("useTrajectorySession", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    historyMock.mockReset();
    streamUrlMock.mockClear();
    historyMock.mockResolvedValue({
      thread_id: "T1",
      events: [toolEvent],
      next_before_seq: null,
      has_more: false,
    });
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads history and appends live SSE events while visible", async () => {
    const { result } = renderHook(() =>
      useTrajectorySession({
        agentId: "A1",
        threadId: "T1",
        visible: true,
      }),
    );

    await waitFor(() => expect(result.current.events).toHaveLength(1));
    expect(historyMock).toHaveBeenCalledWith("A1", "T1");
    expect(MockEventSource.instances).toHaveLength(1);
    expect(streamUrlMock).toHaveBeenCalledWith("A1", "T1", 1);

    act(() => {
      MockEventSource.instances[0].emit("event", assistantEvent);
    });

    expect(result.current.events.map((row) => row.event_id)).toEqual([
      "tool-1",
      "asst-1",
    ]);
  });

  it("does not fetch or subscribe while the panel is hidden", async () => {
    renderHook(() =>
      useTrajectorySession({
        agentId: "A1",
        threadId: "T1",
        visible: false,
      }),
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(historyMock).not.toHaveBeenCalled();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("clears events when the thread changes before the next page loads", async () => {
    const { result, rerender } = renderHook(
      ({ threadId }: { threadId: string }) =>
        useTrajectorySession({
          agentId: "A1",
          threadId,
          visible: true,
        }),
      { initialProps: { threadId: "T1" } },
    );

    await waitFor(() => expect(result.current.events).toHaveLength(1));

    let resolveNext: ((value: unknown) => void) | undefined;
    historyMock.mockReturnValue(
      new Promise((resolve) => {
        resolveNext = resolve;
      }),
    );

    rerender({ threadId: "T2" });

    await waitFor(() => expect(result.current.events).toEqual([]));
    expect(resolveNext).toBeTypeOf("function");
  });

  it("loadEarlier prepends older events and fetches with beforeSeq", async () => {
    const olderEvent = event({
      event_id: "tool-0",
      kind: "tool",
      seq: 0,
    });

    historyMock
      .mockResolvedValueOnce({
        thread_id: "T1",
        events: [toolEvent],
        next_before_seq: 5,
        has_more: true,
      })
      .mockResolvedValueOnce({
        thread_id: "T1",
        events: [olderEvent],
        next_before_seq: null,
        has_more: false,
      });

    const { result } = renderHook(() =>
      useTrajectorySession({
        agentId: "A1",
        threadId: "T1",
        visible: true,
      }),
    );

    await waitFor(() => expect(result.current.events).toHaveLength(1));
    expect(result.current.hasMore).toBe(true);

    await act(async () => {
      await result.current.loadEarlier();
    });

    expect(historyMock).toHaveBeenLastCalledWith("A1", "T1", { beforeSeq: 5 });
    expect(result.current.events.map((row) => row.event_id)).toEqual([
      "tool-0",
      "tool-1",
    ]);
    expect(result.current.hasMore).toBe(false);
  });

  it("loadEarlier ignores stale responses after thread change", async () => {
    const staleOlderEvent = event({
      event_id: "stale-old",
      kind: "tool",
      seq: 0,
    });
    const t2Event = event({
      event_id: "tool-t2",
      kind: "tool",
      seq: 1,
      thread_id: "T2",
    });

    let resolveEarlier: ((value: unknown) => void) | undefined;

    historyMock
      .mockResolvedValueOnce({
        thread_id: "T1",
        events: [toolEvent],
        next_before_seq: 5,
        has_more: true,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveEarlier = resolve;
          }),
      )
      .mockResolvedValueOnce({
        thread_id: "T2",
        events: [t2Event],
        next_before_seq: null,
        has_more: false,
      });

    const { result, rerender } = renderHook(
      ({ threadId }: { threadId: string }) =>
        useTrajectorySession({
          agentId: "A1",
          threadId,
          visible: true,
        }),
      { initialProps: { threadId: "T1" } },
    );

    await waitFor(() => expect(result.current.events).toHaveLength(1));

    let loadEarlierPromise: Promise<void> | undefined;
    act(() => {
      loadEarlierPromise = result.current.loadEarlier();
    });

    rerender({ threadId: "T2" });

    await waitFor(() =>
      expect(result.current.events.map((row) => row.event_id)).toEqual([
        "tool-t2",
      ]),
    );

    await act(async () => {
      resolveEarlier?.({
        thread_id: "T1",
        events: [staleOlderEvent],
        next_before_seq: null,
        has_more: false,
      });
      await loadEarlierPromise;
    });

    expect(result.current.events.map((row) => row.event_id)).toEqual([
      "tool-t2",
    ]);
  });

  it("closes the EventSource when the panel is hidden", async () => {
    const { rerender } = renderHook(
      ({ visible }: { visible: boolean }) =>
        useTrajectorySession({
          agentId: "A1",
          threadId: "T1",
          visible,
        }),
      { initialProps: { visible: true } },
    );

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));

    rerender({ visible: false });

    expect(MockEventSource.instances[0].close).toHaveBeenCalled();
  });
});
