import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TokenCounter from "./TokenCounter";
import type { TokenUsage } from "../../../api/types/chat";

// Mock the chatStore module so tests do not touch the real module-scoped
// session map. useSyncExternalStore reads runUsage via getSnapshot and
// resubscribes via subscribe() on every sessionId change.
const subscribeImpl = vi.fn(
  (_sessionId: string, _listener: () => void) => () => {},
);
const getSnapshotImpl = vi.fn((_sessionId: string) =>
  cachedSnapshot(_sessionId, () => ({
    messages: [],
    isStreaming: false,
    thinkingStartedAt: null,
    runUsage: null,
    contextUsage: null,
    historyHasMore: false,
    historyLoadingMore: false,
    historyNextOffset: 0,
    historyHydrated: false,
  })),
);

// Stable snapshot cache so useSyncExternalStore does not loop. Without
// caching, React calls getSnapshot() multiple times per render; if each
// call returns a fresh object literal, useSyncExternalStore detects the
// change every time and re-renders forever. The real chatStore.getSnapshot
// returns a cached `_snapshot` reference between notifies — the mock must
// mirror that.
const snapshotCache = new Map<string, ReturnType<typeof getSnapshotImpl>>();

function cachedSnapshot(
  sessionId: string,
  build: () => ReturnType<typeof getSnapshotImpl>,
): ReturnType<typeof getSnapshotImpl> {
  // Cache key = sessionId + JSON of the snapshot. Rebuilding on change is
  // cheap because mocks run in microseconds.
  const next = build();
  const cached = snapshotCache.get(sessionId);
  if (cached && JSON.stringify(cached) === JSON.stringify(next)) {
    return cached;
  }
  snapshotCache.set(sessionId, next);
  return next;
}

vi.mock("../hooks/chatStore", () => ({
  getSnapshot: (...args: unknown[]) =>
    getSnapshotImpl(args[0] as string) as ReturnType<typeof getSnapshotImpl>,
  subscribe: (...args: unknown[]) =>
    subscribeImpl(args[0] as string, args[1] as () => void),
}));

const SESSION_ID = "test-session-token-counter";

function snapshotFor(
  sessionId: string,
  runUsage: TokenUsage | null,
): ReturnType<typeof getSnapshotImpl> {
  return cachedSnapshot(sessionId, () => {
    if (sessionId !== SESSION_ID) {
      return {
        messages: [],
        isStreaming: false,
        thinkingStartedAt: null,
        runUsage: null,
        contextUsage: null,
        historyHasMore: false,
        historyLoadingMore: false,
        historyNextOffset: 0,
        historyHydrated: false,
      };
    }
    return {
      messages: [],
      isStreaming: false,
      thinkingStartedAt: null,
      runUsage,
      contextUsage: null,
      historyHasMore: false,
      historyLoadingMore: false,
      historyNextOffset: 0,
      historyHydrated: false,
    };
  });
}

afterEach(() => {
  subscribeImpl.mockClear();
  getSnapshotImpl.mockClear();
  snapshotCache.clear();
  // Default to "no usage" so a stale mock from a prior test does not leak.
  getSnapshotImpl.mockImplementation((sessionId: string) =>
    snapshotFor(sessionId, null),
  );
});

describe("TokenCounter", () => {
  it("renders the current text token count after the encoder warms up", async () => {
    const { getByTestId } = render(
      <TokenCounter text="hello world" sessionId={SESSION_ID} />,
    );
    const chip = getByTestId("token-counter-chip");
    // js-tiktoken cl100k_base: "hello world" → 2 tokens.
    await waitFor(() => {
      expect(chip.textContent).toContain("2");
    });
  });

  it("renders 0 while text is empty", async () => {
    const { getByTestId } = render(
      <TokenCounter text="" sessionId={SESSION_ID} />,
    );
    const chip = getByTestId("token-counter-chip");
    await waitFor(() => {
      expect(chip.textContent).toContain("0");
    });
  });

  it("does not open a popover when there is no per-turn usage yet", async () => {
    const { queryByTestId, getByTestId } = render(
      <TokenCounter text="hi" sessionId={SESSION_ID} />,
    );
    const chip = getByTestId("token-counter-chip");
    fireEvent.click(chip);
    // No usage → no popover, no panel.
    expect(queryByTestId("token-counter-panel")).toBeNull();
  });

  it("shows the run-usage breakdown when chatStore publishes usage", async () => {
    // Seed runUsage for the session. useSyncExternalStore re-reads via
    // getSnapshot every time subscribe() notifies; simulate an SSE usage
    // chunk by invoking the captured listener.
    const usage: TokenUsage = {
      input_tokens: 123,
      output_tokens: 45,
      cache_read_tokens: 80,
      cache_write_tokens: 7,
      total_tokens: 168,
      model_calls: 1,
    };
    getSnapshotImpl.mockImplementation((sessionId: string) =>
      snapshotFor(sessionId, usage),
    );

    let listener: () => void = () => {};
    subscribeImpl.mockImplementation(
      (_sessionId: string, fn: () => void) => {
        listener = fn;
        return () => {};
      },
    );

    const { getByTestId } = render(
      <TokenCounter text="" sessionId={SESSION_ID} />,
    );
    listener();

    const chip = getByTestId("token-counter-chip");
    fireEvent.click(chip);

    const panel = await waitFor(() => getByTestId("token-counter-panel"));
    expect(panel.textContent).toContain("123");
    expect(panel.textContent).toContain("45");
    expect(panel.textContent).toContain("80");
    expect(panel.textContent).toContain("7");
    expect(panel.textContent).toContain("168");
    expect(panel.textContent).toContain("1");
  });

  it("hides the popover entirely when no sessionId is provided", async () => {
    const { getByTestId, queryByTestId } = render(
      <TokenCounter text="some text" sessionId={null} />,
    );
    const chip = getByTestId("token-counter-chip");
    fireEvent.click(chip);
    expect(queryByTestId("token-counter-panel")).toBeNull();
  });

  it("does not open a popover when runUsage has no model calls yet", async () => {
    // Seed usage with model_calls = 0 (e.g. user sent but model has not
    // emitted a usage chunk). showUsage should stay false, so no popover.
    getSnapshotImpl.mockImplementation((sessionId: string) =>
      snapshotFor(sessionId, {
        input_tokens: 10,
        output_tokens: 5,
        total_tokens: 15,
        model_calls: 0,
      }),
    );

    const { queryByTestId, getByTestId } = render(
      <TokenCounter text="" sessionId={SESSION_ID} />,
    );
    fireEvent.click(getByTestId("token-counter-chip"));
    expect(queryByTestId("token-counter-panel")).toBeNull();
  });

  it("renders the cache hit rate as a percentage next to the cache-hit count", async () => {
    // cache_read 80, uncached_input 20 → 80 / (80 + 20) = 80%
    getSnapshotImpl.mockImplementation((sessionId: string) =>
      snapshotFor(sessionId, {
        input_tokens: 100,
        uncached_input_tokens: 20,
        output_tokens: 5,
        cache_read_tokens: 80,
        total_tokens: 105,
        model_calls: 1,
      }),
    );

    let listener: () => void = () => {};
    subscribeImpl.mockImplementation(
      (_sessionId: string, fn: () => void) => {
        listener = fn;
        return () => {};
      },
    );

    const { getByTestId, queryByTestId } = render(
      <TokenCounter text="" sessionId={SESSION_ID} />,
    );
    listener();
    fireEvent.click(getByTestId("token-counter-chip"));

    const hint = await waitFor(() => getByTestId("token-counter-hint"));
    expect(hint.textContent).toBe("80%");
    // Exactly one hint element — other rows have no hint.
    expect(queryByTestId("token-counter-hint") === hint).toBe(true);
  });

  it("renders 100% when all input was served from cache", async () => {
    getSnapshotImpl.mockImplementation((sessionId: string) =>
      snapshotFor(sessionId, {
        input_tokens: 50,
        uncached_input_tokens: 0,
        output_tokens: 5,
        cache_read_tokens: 50,
        total_tokens: 55,
        model_calls: 1,
      }),
    );

    let listener: () => void = () => {};
    subscribeImpl.mockImplementation(
      (_sessionId: string, fn: () => void) => {
        listener = fn;
        return () => {};
      },
    );

    const { getByTestId } = render(
      <TokenCounter text="" sessionId={SESSION_ID} />,
    );
    listener();
    fireEvent.click(getByTestId("token-counter-chip"));

    const hint = await waitFor(() => getByTestId("token-counter-hint"));
    expect(hint.textContent).toBe("100%");
  });

  it("renders '—' for the hit rate when no cache data is reported", async () => {
    // No cache_read or uncached_input — model does not support caching.
    getSnapshotImpl.mockImplementation((sessionId: string) =>
      snapshotFor(sessionId, {
        input_tokens: 50,
        output_tokens: 5,
        total_tokens: 55,
        model_calls: 1,
      }),
    );

    let listener: () => void = () => {};
    subscribeImpl.mockImplementation(
      (_sessionId: string, fn: () => void) => {
        listener = fn;
        return () => {};
      },
    );

    const { getByTestId } = render(
      <TokenCounter text="" sessionId={SESSION_ID} />,
    );
    listener();
    fireEvent.click(getByTestId("token-counter-chip"));

    const hint = await waitFor(() => getByTestId("token-counter-hint"));
    expect(hint.textContent).toBe("—");
  });
});