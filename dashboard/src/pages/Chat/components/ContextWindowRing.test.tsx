import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ContextUsageBreakdown } from "../../../api/modules/octopThreads";
import ContextWindowRing from "./ContextWindowRing";

const contextUsage = vi.hoisted(() => vi.fn());

vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: {
    contextUsage: (...args: unknown[]) => contextUsage(...args),
  },
}));

const HINT = 128_000;
const MAX = 128_000;

function breakdown(used: number, max = MAX): ContextUsageBreakdown {
  return {
    max_tokens: max,
    used_tokens: used,
    segments: [{ key: "conversation", tokens: used }],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderRing(overrides: Record<string, unknown> = {}) {
  const props = {
    usedTokens: HINT,
    maxTokens: MAX,
    agentId: "agent-1",
    threadId: "thread-1",
    isStreaming: false,
    ...overrides,
  };
  return render(<ContextWindowRing {...(props as never)} />);
}

function rerenderRing(view: ReturnType<typeof render>, isStreaming: boolean) {
  return view.rerender(
    <ContextWindowRing
      usedTokens={HINT}
      maxTokens={MAX}
      agentId="agent-1"
      threadId="thread-1"
      isStreaming={isStreaming}
    />,
  );
}

function ringPct(): string | null {
  return screen.getByRole("progressbar").getAttribute("aria-valuenow");
}

describe("ContextWindowRing after compaction", () => {
  beforeEach(() => {
    contextUsage.mockReset();
  });

  it("drops to the server snapshot when a turn ends with less context", async () => {
    // /compact shrinks the thread with no model call: hint stays pre-compaction.
    contextUsage.mockResolvedValue(breakdown(70_400));
    const view = renderRing({ isStreaming: true });
    expect(ringPct()).toBe("100");

    // Turn ended: refetch on the streaming→idle edge.
    rerenderRing(view, false);

    await waitFor(() => expect(ringPct()).toBe("55"));
  });

  it("lets a newer stream hint win again after the snapshot", async () => {
    contextUsage.mockResolvedValue(breakdown(70_400));
    const view = renderRing({ isStreaming: true });
    rerenderRing(view, false);
    await waitFor(() => expect(ringPct()).toBe("55"));

    // A newer hint wins over the snapshot.
    view.rerender(
      <ContextWindowRing
        usedTokens={80_000}
        maxTokens={MAX}
        agentId="agent-1"
        threadId="thread-1"
        isStreaming={false}
      />,
    );

    await waitFor(() => expect(ringPct()).toBe("63"));
  });

  it("ignores a snapshot that resolves after a newer one", async () => {
    const older = deferred<ContextUsageBreakdown>();
    const newer = deferred<ContextUsageBreakdown>();
    contextUsage
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);

    const view = renderRing({ isStreaming: true });
    // First turn ends, then a second begins and ends while the first is open.
    rerenderRing(view, false);
    rerenderRing(view, true);
    rerenderRing(view, false);
    await waitFor(() => expect(contextUsage).toHaveBeenCalledTimes(2));

    newer.resolve(breakdown(70_400));
    await act(async () => {
      await newer.promise;
    });
    expect(ringPct()).toBe("55");

    // The superseded response lands last and must not restore the old value.
    older.resolve(breakdown(HINT));
    await act(async () => {
      await older.promise;
    });
    expect(ringPct()).toBe("55");
  });

  it("refetches after a failed post-compaction refetch instead of reusing the cache", async () => {
    contextUsage
      .mockResolvedValueOnce(breakdown(HINT))
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(breakdown(70_400));

    const view = renderRing({ isStreaming: true });

    // Popover toggles on click: open, read the cached full snapshot, close.
    fireEvent.click(screen.getByRole("progressbar"));
    await waitFor(() => expect(contextUsage).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("progressbar"));

    // Turn ended, but the refetch failed: the cached full snapshot is now
    // untrustworthy, so the next open must go back to the server.
    rerenderRing(view, false);
    await waitFor(() => expect(contextUsage).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole("progressbar"));
    await waitFor(() => expect(contextUsage).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(ringPct()).toBe("55"));
  });
});
