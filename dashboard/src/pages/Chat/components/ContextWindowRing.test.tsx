import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ContextWindowRing from "./ContextWindowRing";

const { contextUsage } = vi.hoisted(() => ({ contextUsage: vi.fn() }));

vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: { contextUsage },
}));

vi.mock("../hooks/useSessions", () => ({
  isPendingThread: () => false,
}));

vi.mock("antd", () => ({
  Popover: ({ children }: { children: React.ReactNode }) => children,
  Spin: () => null,
  Drawer: ({ children }: { children: React.ReactNode }) => children,
}));

describe("ContextWindowRing", () => {
  beforeEach(() => {
    contextUsage.mockReset();
  });

  it("displays a live snapshot instead of a billed-token hint", async () => {
    contextUsage.mockResolvedValueOnce({
      max_tokens: 100_000,
      used_tokens: 20_000,
      available: true,
      segments: [],
    });

    render(
      <ContextWindowRing
        usedTokens={30_000}
        maxTokens={100_000}
        agentId="agent"
        threadId="thread"
      />,
    );

    await waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute(
        "aria-valuenow",
        "20",
      ),
    );
    expect(contextUsage).toHaveBeenCalledWith("agent", "thread", {
      maxTokens: 100_000,
    });
  });

  it("shows unknown instead of a billed-token hint without a snapshot", async () => {
    contextUsage.mockResolvedValueOnce({
      max_tokens: 100_000,
      used_tokens: 30_000,
      available: false,
      segments: [],
    });

    render(
      <ContextWindowRing
        usedTokens={30_000}
        maxTokens={100_000}
        agentId="agent"
        threadId="thread"
      />,
    );

    await waitFor(() => expect(contextUsage).toHaveBeenCalledOnce());
    expect(screen.getByRole("img")).not.toHaveAttribute("aria-valuenow");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("keeps a zero snapshot for the current thread when an older request arrives late", async () => {
    let resolveFirst!: (value: object) => void;
    const first = new Promise<object>((resolve) => {
      resolveFirst = resolve;
    });
    contextUsage.mockImplementation((_agentId: string, threadId: string) =>
      threadId === "first"
        ? first
        : Promise.resolve({
            max_tokens: 100_000,
            used_tokens: 0,
            available: true,
            segments: [],
          }),
    );

    const { rerender } = render(
      <ContextWindowRing
        usedTokens={30_000}
        maxTokens={100_000}
        agentId="agent"
        threadId="first"
      />,
    );
    await waitFor(() => expect(contextUsage).toHaveBeenCalledOnce());

    rerender(
      <ContextWindowRing
        usedTokens={30_000}
        maxTokens={100_000}
        agentId="agent"
        threadId="second"
      />,
    );
    await waitFor(() => expect(contextUsage).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute(
        "aria-valuenow",
        "0",
      ),
    );

    await act(async () => {
      resolveFirst({
        max_tokens: 100_000,
        used_tokens: 90_000,
        available: true,
        segments: [],
      });
    });

    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
  });
});
