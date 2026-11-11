import { afterEach, describe, expect, it } from "vitest";
import {
  getSnapshot,
  ingestHarnessChunk,
  removeSession,
  setSessionTeamRoom,
} from "./chatStore";

const SESSION = "test-decision-notice";

describe("decision notice", () => {
  afterEach(() => {
    removeSession(SESSION);
  });

  it("shows one chip and keeps it on the answer", () => {
    ingestHarnessChunk(SESSION, {
      type: "custom",
      data: {
        kind: "decision",
        model: "typesafe/jev-1.13",
        empty: false,
        parts: [{ kind: "skill", kept: [{ name: "pdf", score: 0.87 }] }],
      },
    });
    ingestHarnessChunk(SESSION, {
      type: "token",
      node: "agent",
      content: "好的",
    });
    const messages = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(messages).toHaveLength(1);
    expect(messages[0]?.content).toBe("好的");
    expect(messages[0]?.decision).toMatchObject({
      model: "typesafe/jev-1.13",
      parts: [{ kind: "skill", kept: [{ name: "pdf", score: 0.87 }] }],
    });
  });

  it("updates the same chip when the model runs again", () => {
    ingestHarnessChunk(SESSION, {
      type: "custom",
      data: {
        kind: "decision",
        model: "laya",
        empty: true,
        parts: [],
      },
    });
    ingestHarnessChunk(SESSION, {
      type: "custom",
      data: {
        kind: "decision",
        model: "laya",
        empty: false,
        parts: [{ kind: "tool", kept: [{ name: "read_pdf" }] }],
      },
    });
    const messages = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(messages).toHaveLength(1);
    expect(messages[0]?.decision?.empty).toBe(false);
    expect(messages[0]?.decision?.parts[0]?.kind).toBe("tool");
  });

  it("keeps a host result review on the wrap-up", () => {
    setSessionTeamRoom(SESSION, true);
    ingestHarnessChunk(
      SESSION,
      {
        type: "custom",
        agent_id: "host",
        team_wrapup: true,
        data: {
          kind: "decision",
          model: "laya",
          empty: false,
          parts: [
            {
              kind: "result",
              kept: [{ name: "结果充分, 可以总结", score: 0.91 }],
            },
          ],
        },
      },
      "host",
    );
    const message = getSnapshot(SESSION).messages.find(
      (item) => item.role === "assistant" && item.teamWrapup,
    );
    expect(message?.decision?.parts[0]).toEqual({
      kind: "result",
      kept: [{ name: "结果充分, 可以总结", score: 0.91 }],
    });
  });

  it("keeps the notice when a tool call starts", () => {
    ingestHarnessChunk(SESSION, {
      type: "custom",
      data: {
        kind: "decision",
        model: "typesafe/jev-1.13",
        empty: false,
        parts: [{ kind: "tool", kept: [{ name: "task" }] }],
      },
    });
    ingestHarnessChunk(SESSION, {
      type: "tool_call_chunk",
      node: "agent",
      index: 0,
      id: "call-1",
      name: "read_file",
      args: "{}",
    });
    const messages = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(messages.some((message) => message.decision)).toBe(true);
    expect(
      messages.some((message) => message.toolData?.name === "read_file"),
    ).toBe(true);
  });

  it("pins an unlabeled decision onto the team host bubble", () => {
    setSessionTeamRoom(SESSION, true);
    ingestHarnessChunk(
      SESSION,
      {
        type: "custom",
        data: {
          kind: "decision",
          model: "laya",
          empty: false,
          parts: [{ kind: "member", kept: [{ name: "研究员", score: 0.91 }] }],
        },
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      { type: "token", agent_id: "host", content: "交给研究员" },
      "host",
    );
    const messages = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant",
    );
    expect(messages).toHaveLength(1);
    expect(messages[0]?.speakerAgentId).toBe("host");
    expect(messages[0]?.content).toBe("交给研究员");
    expect(messages[0]?.decision?.parts[0]?.kind).toBe("member");
  });

  it("puts a wrap-up decision on a new host bubble", () => {
    setSessionTeamRoom(SESSION, true);
    ingestHarnessChunk(
      SESSION,
      { type: "token", agent_id: "host", content: "交给研究员" },
      "host",
    );
    ingestHarnessChunk(SESSION, { type: "done", agent_id: "host" }, "host");
    ingestHarnessChunk(
      SESSION,
      {
        type: "custom",
        agent_id: "host",
        team_wrapup: true,
        data: {
          kind: "decision",
          model: "laya",
          empty: false,
          parts: [{ kind: "member", kept: [] }],
        },
      },
      "host",
    );
    ingestHarnessChunk(
      SESSION,
      {
        type: "token",
        agent_id: "host",
        team_wrapup: true,
        content: "可以收工",
      },
      "host",
    );
    const host = getSnapshot(SESSION).messages.filter(
      (message) => message.role === "assistant" && !message.toolData,
    );
    expect(host).toHaveLength(2);
    expect(host[0]?.content).toBe("交给研究员");
    expect(host[0]?.decision).toBeUndefined();
    expect(host[1]?.teamWrapup).toBe(true);
    expect(host[1]?.content).toBe("可以收工");
    expect(host[1]?.decision?.parts[0]).toMatchObject({
      kind: "member",
      kept: [],
    });
  });
});
