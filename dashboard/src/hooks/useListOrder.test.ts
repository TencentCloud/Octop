import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OctopAgent } from "../context/AgentContext";
import * as AgentContextModule from "../context/AgentContext";
import { useListOrder, deriveListOrderFromAgents } from "./useListOrder";

/** Build a minimal agent fixture carrying only the ordering fields. */
function agent(id: string, extra: Partial<OctopAgent> = {}): OctopAgent {
  return {
    id: 0,
    agent_id: id,
    name: id,
    description: null,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: null,
    state: "running",
    last_error: null,
    icon: null,
    icon_name: null,
    icon_url: null,
    color: null,
    config: {},
    ...extra,
  } as OctopAgent;
}

function setupAgents(
  mockAgents: OctopAgent[],
  pinAgent?: (id: string, pinned: boolean) => Promise<void>,
  reorderAgents?: (order: string[]) => Promise<void>,
  loading = false,
) {
  const pin =
    pinAgent ?? (vi.fn(async () => undefined) as (id: string, p: boolean) => Promise<void>);
  const reorder =
    reorderAgents ??
    (vi.fn(async () => undefined) as (order: string[]) => Promise<void>);
  const value: AgentContextModule.AgentContextValue = {
    agents: mockAgents,
    activeAgentId: null,
    activeAgent: null,
    loading,
    error: null,
    setActiveAgent: () => undefined,
    refresh: async () => undefined,
    pinAgent: pin,
    reorderAgents: reorder,
  };
  vi.spyOn(AgentContextModule, "useAgent").mockImplementation(
    () => value as ReturnType<typeof AgentContextModule.useAgent>,
  );
  return { pin, reorder, value };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("deriveListOrderFromAgents", () => {
  it("reads pinned membership and sort_order, skipping un-ordered agents", () => {
    const agents = [
      agent("a", { pinned: true, sort_order: 2 }),
      agent("b", { sort_order: 0 }),
      agent("c", { sort_order: 1 }),
      agent("d", { sort_order: -1 }),
      agent("e"),
    ];
    expect(deriveListOrderFromAgents(agents)).toEqual({
      pinned: ["a"],
      order: ["b", "c", "a"],
    });
  });

  it("returns an empty state for an empty agent list", () => {
    expect(deriveListOrderFromAgents([])).toEqual({ pinned: [], order: [] });
  });
});

describe("useListOrder", () => {
  it("derives state from loaded agents (no localStorage involved)", () => {
    setupAgents([
      agent("a", { pinned: true }),
      agent("b", { sort_order: 0 }),
    ]);

    const { result } = renderHook(() => useListOrder());
    expect(result.current.state).toEqual({ pinned: ["a"], order: ["b"] });
    expect(result.current.loading).toBe(false);
  });

  it("keeps an empty (stable) state while agents are still loading", () => {
    setupAgents([], undefined, undefined, true);
    const { result } = renderHook(() => useListOrder());
    expect(result.current.loading).toBe(true);
    expect(result.current.state).toEqual({ pinned: [], order: [] });
  });

  it("write() routes the sequence to reorderAgents and awaits it", async () => {
    const { reorder } = setupAgents([]);
    const { result } = renderHook(() => useListOrder());

    await act(async () => {
      await result.current.write({
        pinned: [],
        order: ["b", "a"],
      });
    });
    expect(reorder).toHaveBeenCalledWith(["b", "a"]);
  });

  it("write() is a no-op for an empty manual order", async () => {
    const { reorder } = setupAgents([]);
    const { result } = renderHook(() => useListOrder());

    await act(async () => {
      await result.current.write({ pinned: [], order: [] });
    });
    expect(reorder).not.toHaveBeenCalled();
  });

  it("togglePin() flips membership and routes through pinAgent", async () => {
    const { pin } = setupAgents([agent("a", { pinned: true })]);
    const { result } = renderHook(() => useListOrder());

    await act(async () => {
      await result.current.togglePin("a");
    });
    expect(pin).toHaveBeenCalledWith("a", false);
  });

  it("propagates backend failures so the caller can surface/rollback", async () => {
    const agents = [agent("a"), agent("b")];
    const failingReorder = vi.fn(async () => {
      throw new Error("offline");
    });
    setupAgents(agents, undefined, failingReorder);
    const { result } = renderHook(() => useListOrder());

    await expect(
      result.current.write({ pinned: [], order: ["a", "b"] }),
    ).rejects.toThrow("offline");
  });
});
