import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import type { OctopAgent } from "../../../context/AgentContext";
import { useExpertSessionCatalog } from "./useExpertSessionCatalog";
import { emitSessionEvent } from "./chatStore";

const agents = [{ agent_id: "agent", state: "running" }] as OctopAgent[];
const row = (id: string, archived = false) => ({
  thread_id: id,
  title: id,
  last_active: 1,
  channel_type: "dashboard",
  session_key: "key",
  archived,
});

afterEach(() => vi.restoreAllMocks());

describe("useExpertSessionCatalog archive views", () => {
  it("does not resurrect an archived session from an in-flight catalog request", async () => {
    let resolveList!: (rows: ReturnType<typeof row>[]) => void;
    vi.spyOn(octopThreadsApi, "list").mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveList = resolve;
        }),
    );
    const { result } = renderHook(() => useExpertSessionCatalog(agents, true));
    act(() =>
      emitSessionEvent({ kind: "sessionDeleted", sessionId: "archived-now" }),
    );
    await act(async () => resolveList([row("archived-now"), row("keep")]));
    expect(result.current.byAgent.agent.map((session) => session.id)).toEqual([
      "keep",
    ]);
  });
  it("drops a session archived or deleted by the active expert", async () => {
    vi.spyOn(octopThreadsApi, "list").mockResolvedValue([row("current")]);
    const { result } = renderHook(() => useExpertSessionCatalog(agents, true));
    await waitFor(() =>
      expect(result.current.byAgent.agent?.[0].id).toBe("current"),
    );
    act(() =>
      emitSessionEvent({ kind: "sessionDeleted", sessionId: "current" }),
    );
    expect(result.current.byAgent.agent).toEqual([]);
  });
  it("hides the previous view while loading its replacement", async () => {
    const list = vi
      .spyOn(octopThreadsApi, "list")
      .mockResolvedValueOnce([row("current")]);
    let resolveArchived!: (rows: ReturnType<typeof row>[]) => void;
    list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveArchived = resolve;
        }),
    );
    const { result, rerender } = renderHook(
      ({ archived }) =>
        useExpertSessionCatalog(agents, true, undefined, archived),
      { initialProps: { archived: false } },
    );
    await waitFor(() =>
      expect(result.current.byAgent.agent?.[0].id).toBe("current"),
    );

    rerender({ archived: true });
    expect(result.current.byAgent).toEqual({});
    expect(list).toHaveBeenLastCalledWith("agent", 100, true);
    await act(async () => resolveArchived([row("archived", true)]));
    expect(result.current.byAgent.agent.map((session) => session.id)).toEqual([
      "archived",
    ]);
  });

  it("discards a current response arriving after the archived response", async () => {
    let resolveCurrent!: (rows: ReturnType<typeof row>[]) => void;
    vi.spyOn(octopThreadsApi, "list")
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveCurrent = resolve;
          }),
      )
      .mockResolvedValueOnce([row("archived", true)]);
    const { result, rerender } = renderHook(
      ({ archived }) =>
        useExpertSessionCatalog(agents, true, undefined, archived),
      { initialProps: { archived: false } },
    );
    rerender({ archived: true });
    await waitFor(() =>
      expect(result.current.byAgent.agent?.[0].id).toBe("archived"),
    );
    await act(async () => resolveCurrent([row("stale-current")]));
    expect(result.current.byAgent.agent[0].id).toBe("archived");
  });
});
