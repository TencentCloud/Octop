import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  getSnapshot,
  ingestHarnessChunk,
  removeSession,
  sendTurn,
  setSessionTeamRoom,
} from "./chatStore";

const SESSION = "test-team-stream";

describe("team member live stream", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  beforeEach(() => {
    setSessionTeamRoom(SESSION, true);
  });

  it("keeps member thinking and tools off the host bubble", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "I will ask the doctor.",
    });
    ingestHarnessChunk(SESSION, {
      type: "tool_call_chunk",
      id: "host-ask",
      name: "ask_agent",
      args: "{}",
    });
    ingestHarnessChunk(SESSION, {
      type: "reasoning",
      content: "review the labs",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, {
      type: "tool_call_chunk",
      id: "doc-read",
      name: "read_file",
      args: "{}",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "please rest",
      agent_id: "doctor",
    });

    const { messages } = getSnapshot(SESSION);
    const hostText = messages.find(
      (item) => item.content.includes("I will ask") && !item.speakerAgentId,
    );
    const hostTool = messages.find(
      (item) => item.toolData?.name === "ask_agent",
    );
    const memberThink = messages.find(
      (item) =>
        item.speakerAgentId === "doctor" &&
        item.contentBlocks?.some((block) => block.type === "thinking"),
    );
    const memberTool = messages.find(
      (item) =>
        item.speakerAgentId === "doctor" && item.toolData?.name === "read_file",
    );
    const memberText = messages.find(
      (item) =>
        item.speakerAgentId === "doctor" &&
        item.content.includes("please rest"),
    );

    expect(hostText?.content).toContain("I will ask");
    expect(hostTool?.toolData?.name).toBe("ask_agent");
    expect(memberThink?.contentBlocks?.[0]).toMatchObject({
      type: "thinking",
      content: "review the labs",
    });
    expect(memberTool?.toolData?.name).toBe("read_file");
    expect(memberText?.content).toBe("please rest");
    expect(
      hostText?.contentBlocks?.some((block) => block.type === "thinking"),
    ).not.toBe(true);
  });

  it("keeps host text on one bubble across ask_agent", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "已安排健康管理专家为你解答，稍等片刻",
      agent_id: "host",
    });
    ingestHarnessChunk(SESSION, {
      type: "tool_call_chunk",
      id: "host-ask",
      name: "ask_agent",
      args: "{}",
      agent_id: "host",
    });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "这个问题交给健康管理专家来回答。",
      agent_id: "host",
    });

    const { messages } = getSnapshot(SESSION);
    const host = messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(1);
    expect(host[0]?.content).toContain("已安排健康管理专家");
    expect(host[0]?.content).toContain("这个问题交给健康管理专家");
  });

  it("does not seal the host when a member done arrives", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "host still talking",
    });
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "member answer",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, { type: "done", agent_id: "doctor" });

    const { messages, isStreaming } = getSnapshot(SESSION);
    const host = messages.find((item) =>
      item.content.includes("host still talking"),
    );
    const member = messages.find((item) => item.speakerAgentId === "doctor");
    expect(host?.status).toBe("streaming");
    expect(member?.status).toBe("done");
    expect(isStreaming).toBe(false);
  });

  it("does not lock the composer on member-only chunks", () => {
    ingestHarnessChunk(SESSION, { type: "done" });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "please rest",
      agent_id: "doctor",
    });
    const { isStreaming, messages } = getSnapshot(SESSION);
    expect(isStreaming).toBe(false);
    expect(
      messages.some(
        (item) =>
          item.speakerAgentId === "doctor" &&
          item.content.includes("please rest"),
      ),
    ).toBe(true);
  });

  it("releases the composer on host done while a member is still streaming", async () => {
    class FakeWebSocket {
      static instances: FakeWebSocket[] = [];
      readyState = 0;
      sent: string[] = [];
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor() {
        FakeWebSocket.instances.push(this);
        queueMicrotask(() => {
          this.readyState = 1;
          this.onopen?.();
        });
      }
      send(data: string) {
        this.sent.push(data);
      }
      close() {
        this.readyState = 3;
        this.onclose?.();
      }
    }

    const RealWS = globalThis.WebSocket;
    FakeWebSocket.instances = [];
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    try {
      const first = sendTurn(
        SESSION,
        "hi",
        "agent-1",
        "",
        undefined,
        undefined,
        null,
        SESSION,
      );
      await Promise.resolve();
      const ws1 = FakeWebSocket.instances[0];
      expect(ws1).toBeDefined();
      ws1.onmessage?.({
        data: JSON.stringify({ type: "token", content: "host talking" }),
      });
      ws1.onmessage?.({
        data: JSON.stringify({
          type: "token",
          content: "member talking",
          agent_id: "doctor",
        }),
      });
      ws1.onmessage?.({ data: JSON.stringify({ type: "done" }) });

      const afterHost = getSnapshot(SESSION);
      expect(afterHost.isStreaming).toBe(false);
      expect(
        afterHost.messages.find((item) => item.speakerAgentId === "doctor")
          ?.status,
      ).toBe("streaming");

      const second = sendTurn(
        SESSION,
        "again",
        "agent-1",
        "",
        undefined,
        undefined,
        null,
        SESSION,
      );
      await Promise.resolve();
      expect(ws1.sent.some((row) => row.includes('"cancel"'))).toBe(false);
      expect(getSnapshot(SESSION).isStreaming).toBe(true);
      expect(FakeWebSocket.instances.length).toBeGreaterThan(1);

      FakeWebSocket.instances[1]?.close();
      ws1.close();
      await Promise.allSettled([first, second]);
    } finally {
      globalThis.WebSocket = RealWS;
    }
  });

  it("keeps member tokens on one bubble after that member is marked done", () => {
    ingestHarnessChunk(SESSION, { type: "token", content: "I will ask." });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "please ",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, { type: "done", agent_id: "doctor" });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "rest",
      agent_id: "doctor",
    });
    const member = getSnapshot(SESSION).messages.filter(
      (item) => item.speakerAgentId === "doctor",
    );
    expect(member).toHaveLength(1);
    expect(member[0]?.content).toBe("please rest");
  });

  it("keeps concurrent host and member tokens on separate bubbles", () => {
    ingestHarnessChunk(
      SESSION,
      { type: "token", content: "已安排", agent_id: "host" },
      "host",
    );
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "这是一个医学",
      agent_id: "doctor",
    });
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "临床辅助专家为您解答，稍等片刻。",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "知识问题，我可以直接回答",
      agent_id: "doctor",
    });
    const { messages } = getSnapshot(SESSION);
    const host = messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    const member = messages.filter((item) => item.speakerAgentId === "doctor");
    expect(host.map((item) => item.content).join("")).toBe(
      "已安排临床辅助专家为您解答，稍等片刻。",
    );
    expect(member).toHaveLength(1);
    expect(member[0]?.content).toBe("这是一个医学知识问题，我可以直接回答");
    expect(host.some((item) => item.content.includes("医学知识"))).toBe(false);
    expect(member[0]?.content.includes("已安排")).toBe(false);
  });

  it("does not merge unlabeled tokens onto a stamped host bubble", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "已安排临床辅助专家为您解答，稍等片刻。",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "这是一个医学知识问题，我可以直接回答",
    });
    const { messages } = getSnapshot(SESSION);
    const assistants = messages.filter((item) => item.role === "assistant");
    expect(assistants).toHaveLength(2);
    expect(
      assistants.find((item) => item.speakerAgentId === "host")?.content,
    ).toBe("已安排临床辅助专家为您解答，稍等片刻。");
    expect(assistants.find((item) => !item.speakerAgentId)?.content).toBe(
      "这是一个医学知识问题，我可以直接回答",
    );
  });

  it("keeps unlabeled solo-chat tokens on one bubble", () => {
    setSessionTeamRoom(SESSION, false);
    ingestHarnessChunk(SESSION, { type: "token", content: "Hel" });
    ingestHarnessChunk(SESSION, { type: "token", content: "lo" });
    ingestHarnessChunk(SESSION, { type: "token", content: "!" });
    const assistants = getSnapshot(SESSION).messages.filter(
      (item) => item.role === "assistant",
    );
    expect(assistants).toHaveLength(1);
    expect(assistants[0]?.content).toBe("Hello!");
    expect(assistants[0]?.speakerAgentId).toBeUndefined();
  });

  it("opens a new host bubble after a member has spoken", () => {
    ingestHarnessChunk(SESSION, { type: "token", content: "A" });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "1",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, { type: "token", content: "B" });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "2",
      agent: "doctor",
    });
    const { messages } = getSnapshot(SESSION);
    const host = messages.filter((item) => !item.speakerAgentId);
    const member = messages.filter((item) => item.speakerAgentId === "doctor");
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toBe("A");
    expect(host[1]?.content).toBe("B");
    expect(member).toHaveLength(1);
    expect(member[0]?.content).toBe("12");
  });

  it("seals a stamped host bubble when the unlabeled host done arrives", () => {
    ingestHarnessChunk(
      SESSION,
      { type: "token", content: "host talking", agent_id: "host" },
      "host",
    );
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "member talking",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, { type: "done" });

    const { messages, isStreaming } = getSnapshot(SESSION);
    const host = messages.find((item) => item.speakerAgentId === "host");
    const member = messages.find((item) => item.speakerAgentId === "doctor");
    expect(host?.status).toBe("done");
    expect(member?.status).toBe("streaming");
    expect(isStreaming).toBe(false);
  });

  it("opens a new stamped host bubble after a member has spoken", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "A",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "1",
        agent_id: "doctor",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      { type: "token", content: "B", agent: "host" },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      { type: "token", content: "2", agent: "doctor" },
      "host",
    );
    const { messages } = getSnapshot(SESSION);
    const host = messages.filter((item) => item.speakerAgentId === "host");
    const member = messages.filter((item) => item.speakerAgentId === "doctor");
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toBe("A");
    expect(host[1]?.content).toBe("B");
    expect(member).toHaveLength(1);
    expect(member[0]?.content).toBe("12");
  });

  it("keeps wrap-up off the dispatch bubble even while the host is still streaming", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "已派给临床辅助专家，稍等片刻。",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "可以收工。",
        agent_id: "host",
        team_wrapup: true,
      },
      "host",
    );
    const host = getSnapshot(SESSION).messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toBe("已派给临床辅助专家，稍等片刻。");
    expect(host[1]?.content).toBe("可以收工。");
    expect(host[1]?.teamWrapup).toBe(true);
  });

  it("opens a new host bubble for the wrap-up after the assignment is sealed", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "已安排健康管理专家为你解答，稍等片刻",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(SESSION, { type: "done" }, "host");
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "睡眠建议已经给出，可以收工。",
        agent_id: "host",
        team_snapshot: true,
      },
      "host",
    );

    const { messages } = getSnapshot(SESSION);
    const host = messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toContain("已安排健康管理专家");
    expect(host[1]?.content).toBe("睡眠建议已经给出，可以收工。");
    expect(host[1]?.status).toBe("done");
  });

  it("does not duplicate a full-message replay onto the host bubble", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "已安排临床助手为您整理心脏病的治疗方案，稍等片刻。",
      agent_id: "host",
    });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "已安排临床助手为您整理心脏病的治疗方案，稍等片刻。",
      agent_id: "host",
    });
    const host = getSnapshot(SESSION).messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(1);
    expect(host[0]?.content).toBe(
      "已安排临床助手为您整理心脏病的治疗方案，稍等片刻。",
    );
  });

  it("opens a new host bubble after members even without team_wrapup", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "已安排健康管理专家为你解答，稍等片刻",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "tool_call_chunk",
        id: "host-ask",
        name: "ask_agent",
        args: "{}",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "tool_result",
        messages: [{ tool_call_id: "host-ask", content: "queued" }],
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(SESSION, { type: "done" }, "host");
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "请先规律作息。",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, { type: "done", agent_id: "doctor" });
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "睡眠建议已经给出，可以收工。",
        agent_id: "host",
      },
      "host",
    );

    const { messages } = getSnapshot(SESSION);
    const host = messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toContain("已安排健康管理专家");
    expect(host[1]?.content).toBe("睡眠建议已经给出，可以收工。");
    expect(host[1]?.status).toBe("streaming");
  });

  it("does not reopen a sealed host bubble after ask_agent completes", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "已派给临床辅助专家，稍等片刻。",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "tool_call_chunk",
        id: "host-ask",
        name: "ask_agent",
        args: "{}",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "tool_result",
        messages: [{ tool_call_id: "host-ask", content: "queued" }],
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(SESSION, { type: "done" }, "host");
    ingestHarnessChunk(
      SESSION,
      { type: "token", content: "可以收工。", agent_id: "host" },
      "host",
    );
    const host = getSnapshot(SESSION).messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toBe("已派给临床辅助专家，稍等片刻。");
    expect(host[1]?.content).toBe("可以收工。");
  });

  it("does not seal dispatch when a wrap-up done arrives", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "已派给临床辅助专家，稍等片刻。",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "可以",
        agent_id: "host",
        team_wrapup: true,
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      { type: "done", agent_id: "host", team_wrapup: true },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      { type: "token", content: "还在调度。", agent_id: "host" },
      "host",
    );
    const host = getSnapshot(SESSION).messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toBe("已派给临床辅助专家，稍等片刻。还在调度。");
    expect(host[0]?.status).toBe("streaming");
    expect(host[1]?.content).toBe("可以");
    expect(host[1]?.status).toBe("done");
  });

  it("streams wrap-up tokens onto a new host bubble", () => {
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "已安排健康管理专家为你解答，稍等片刻",
        agent_id: "host",
      },
      "host",
    );
    ingestHarnessChunk(SESSION, { type: "done" }, "host");
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "睡眠",
        agent_id: "host",
        team_wrapup: true,
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        content: "建议已经给出。",
        agent_id: "host",
        team_wrapup: true,
      },
      "host",
    );

    const { messages } = getSnapshot(SESSION);
    const host = messages.filter(
      (item) => item.speakerAgentId === "host" && !item.toolData,
    );
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toContain("已安排健康管理专家");
    expect(host[1]?.content).toBe("睡眠建议已经给出。");
    expect(host[1]?.status).toBe("streaming");
  });

  it("merges a member snapshot onto the live bubble", () => {
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "please ",
      agent_id: "doctor",
    });
    ingestHarnessChunk(SESSION, { type: "done", agent_id: "doctor" });
    ingestHarnessChunk(SESSION, {
      type: "token",
      content: "please rest",
      agent_id: "doctor",
      team_snapshot: true,
    });
    const { messages } = getSnapshot(SESSION);
    const member = messages.filter((item) => item.speakerAgentId === "doctor");
    expect(member).toHaveLength(1);
    expect(member[0]?.content).toBe("please rest");
    expect(member[0]?.status).toBe("done");
  });
});
