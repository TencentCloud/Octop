import { StrictMode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ThreadSummaryRow,
  ThreadSummarySessionRow,
} from "../../../api/modules/octopThreads";
import { resetSessionInboxForTests, useSessionInbox } from "./useSessionInbox";
import { emitSessionEvent } from "./chatStore";
import { resetSessionStoreForTests } from "./useSessions";

const summaryMock = vi.fn();

vi.mock("../../../api/modules/octopThreads", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/octopThreads")
  >();
  return {
    ...actual,
    octopThreadsApi: {
      ...actual.octopThreadsApi,
      summary: (...args: unknown[]) => summaryMock(...args),
    },
  };
});

function sessionRow(
  overrides: Partial<ThreadSummarySessionRow> = {},
): ThreadSummarySessionRow {
  return {
    agent_id: "agent-a",
    thread_id: "thr_1",
    title: "Pinned chat",
    channel_type: "dashboard",
    last_active: 100,
    created_at: 10,
    has_messages: true,
    pinned: true,
    project_id: null,
    project_name: null,
    ...overrides,
  };
}

function summaryRow(
  overrides: Partial<ThreadSummaryRow> = {},
): ThreadSummaryRow {
  return {
    agent_id: "agent-a",
    session_count: 2,
    has_activity: true,
    last_active: 100,
    pinned: [],
    ...overrides,
  };
}

function renderInbox(key = "user:1") {
  return renderHook(() => useSessionInbox(key), { wrapper: StrictMode });
}

describe("useSessionInbox", () => {
  beforeEach(() => {
    resetSessionInboxForTests();
    resetSessionStoreForTests();
    summaryMock.mockReset();
    summaryMock.mockResolvedValue([
      summaryRow({
        session_count: 2,
        pinned: [sessionRow()],
      }),
    ]);
  });

  it("AC-S0-3: 收件箱聚合请求恰 1 次（StrictMode 双挂载去重）", async () => {
    const { result } = renderInbox();

    await waitFor(() =>
      expect(result.current.inboxByAgent["agent-a"]).toBeDefined(),
    );

    expect(summaryMock).toHaveBeenCalledTimes(1);
    expect(summaryMock).toHaveBeenCalledWith();
    expect(result.current.pinnedSessions.map((s) => s.id)).toEqual(["thr_1"]);
  });

  it("AC-S0-3: agentKey 不变不重发（切 agent / 重渲染 / 展开搜索都不重发）", async () => {
    const { result, rerender } = renderInbox();
    await waitFor(() =>
      expect(result.current.inboxByAgent["agent-a"]).toBeDefined(),
    );

    rerender();
    rerender();
    expect(summaryMock).toHaveBeenCalledTimes(1);

    // Session events are patched locally — never a re-request (S-10 snapshot).
    act(() => {
      emitSessionEvent({ kind: "sessionsChanged", sessionId: "thr_1" });
    });
    expect(summaryMock).toHaveBeenCalledTimes(1);
  });

  it("单源化：agent 级 has_activity 取服务端字段，会话级 hasActivity 走 toSession", async () => {
    // Empty thread: toSession reports hasActivity=false although the agent
    // bucket itself is active — proving neither side is recomputed here.
    summaryMock.mockResolvedValue([
      summaryRow({
        has_activity: true,
        session_count: 1,
        pinned: [
          sessionRow({
            thread_id: "thr_empty",
            title: null,
            has_messages: false,
            last_active: 0,
            created_at: 55,
          }),
        ],
      }),
    ]);

    const { result } = renderInbox();
    await waitFor(() =>
      expect(result.current.inboxByAgent["agent-a"]).toBeDefined(),
    );

    const bucket = result.current.inboxByAgent["agent-a"];
    expect(bucket.hasActivity).toBe(true);
    expect(bucket.sessionCount).toBe(1);
    expect(bucket.lastActive).toBe(100);
    expect(bucket.pinned.map((s) => s.hasActivity)).toEqual([false]);
    // Pinned rows are mapped through toSession, so project fields pass through.
    expect(bucket.pinned[0].agentId).toBe("agent-a");
    expect(bucket.pinned[0].projectId).toBeNull();
  });

  it("透传项目字段：project_id / project_name 进 Session（T2.6 数据源）", async () => {
    summaryMock.mockResolvedValue([
      summaryRow({
        pinned: [
          sessionRow({
            thread_id: "thr_proj",
            project_id: "prj_1",
            project_name: "Apollo",
          }),
        ],
      }),
    ]);

    const { result } = renderInbox();
    await waitFor(() => expect(result.current.pinnedSessions.length).toBe(1));

    expect(result.current.pinnedSessions[0].projectId).toBe("prj_1");
    expect(result.current.pinnedSessions[0].projectName).toBe("Apollo");
    expect(result.current.inboxByAgent["agent-a"].pinned[0].projectName).toBe(
      "Apollo",
    );
  });

  it("sessionDeleted 本地移除，patchSession 本地同步，均不重发请求", async () => {
    const { result } = renderInbox();
    await waitFor(() => expect(result.current.pinnedSessions.length).toBe(1));

    act(() => {
      result.current.patchSession("thr_1", { name: "Renamed" });
    });
    expect(result.current.pinnedSessions[0].name).toBe("Renamed");

    act(() => {
      result.current.patchSession("thr_1", { pinned: false });
    });
    expect(result.current.pinnedSessions).toEqual([]);
    expect(result.current.inboxByAgent["agent-a"].sessionCount).toBe(1);

    act(() => {
      emitSessionEvent({ kind: "sessionDeleted", sessionId: "thr_1" });
    });
    expect(result.current.inboxByAgent["agent-a"].pinned).toEqual([]);
    expect(summaryMock).toHaveBeenCalledTimes(1);
  });

  it("S-10: 手动 refresh 显式重新取数（+1 次请求）", async () => {
    const { result } = renderInbox();
    await waitFor(() =>
      expect(result.current.inboxByAgent["agent-a"]).toBeDefined(),
    );
    expect(summaryMock).toHaveBeenCalledTimes(1);

    summaryMock.mockResolvedValue([summaryRow({ session_count: 5 })]);
    await act(async () => {
      result.current.refresh();
    });

    expect(summaryMock).toHaveBeenCalledTimes(2);
    expect(result.current.inboxByAgent["agent-a"].sessionCount).toBe(5);
  });

  it("缓存按 agentKey 生效：同键重复挂载不重发，换键才新作用域请求", async () => {
    const first = renderInbox("user:1");
    await waitFor(() =>
      expect(first.result.current.inboxByAgent["agent-a"]).toBeDefined(),
    );
    expect(summaryMock).toHaveBeenCalledTimes(1);

    // Same key again (sidebar remount / layout switch) → module cache hit.
    const second = renderInbox("user:1");
    await waitFor(() =>
      expect(second.result.current.pinnedSessions.length).toBe(1),
    );
    expect(summaryMock).toHaveBeenCalledTimes(1);

    // A different scope key is the only thing allowed to start a new request.
    const third = renderInbox("user:2");
    await waitFor(() =>
      expect(third.result.current.inboxByAgent["agent-a"]).toBeDefined(),
    );
    expect(summaryMock).toHaveBeenCalledTimes(2);
  });

  it("收件箱请求失败时保持可用（空快照，不抛出）", async () => {
    summaryMock.mockRejectedValue(new Error("network down"));

    const { result } = renderInbox();
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.inboxByAgent).toEqual({});
    expect(result.current.pinnedSessions).toEqual([]);
  });
});
