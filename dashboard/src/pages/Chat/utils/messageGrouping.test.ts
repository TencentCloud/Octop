import { describe, expect, it } from "vitest";
import type { ChatMessage } from "../hooks/useChat";
import {
  findSpeakerTextToContinue,
  groupConsecutiveAssistantMessages,
  isRoomHostSpeaker,
  sameStreamingSpeaker,
  speakerTurnWasInterrupted,
} from "./messageGrouping";
import { splitAssistantTurn } from "./messageContent";

function msg(
  role: ChatMessage["role"],
  id: string,
  extra?: Partial<ChatMessage>,
): ChatMessage {
  return {
    id,
    role,
    content: extra?.content ?? "",
    status: "done",
    timestamp: Date.now(),
    ...extra,
  };
}

describe("sameStreamingSpeaker", () => {
  it("keeps unlabeled host tokens together and splits a member", () => {
    expect(sameStreamingSpeaker(undefined, undefined)).toBe(true);
    expect(sameStreamingSpeaker("doctor", "doctor")).toBe(true);
    expect(sameStreamingSpeaker(undefined, "doctor")).toBe(false);
    expect(sameStreamingSpeaker("doctor", undefined)).toBe(false);
    expect(sameStreamingSpeaker("doctor", "host")).toBe(false);
  });

  it("aliases unlabeled tokens to the room host in 1:1", () => {
    expect(sameStreamingSpeaker("host", undefined, "host")).toBe(true);
    expect(sameStreamingSpeaker(undefined, "host", "host")).toBe(true);
    expect(sameStreamingSpeaker("host", "host", "host")).toBe(true);
    expect(sameStreamingSpeaker("doctor", undefined, "host")).toBe(false);
    expect(sameStreamingSpeaker("host", "doctor", "host")).toBe(false);
  });

  it("does not treat a missing id as the room host in a team room", () => {
    expect(sameStreamingSpeaker("host", undefined, "host", true)).toBe(false);
    expect(sameStreamingSpeaker(undefined, "host", "host", true)).toBe(false);
    expect(sameStreamingSpeaker("host", "host", "host", true)).toBe(true);
    expect(sameStreamingSpeaker("doctor", undefined, "host", true)).toBe(false);
    expect(sameStreamingSpeaker("host", "doctor", "host", true)).toBe(false);
  });
});

describe("isRoomHostSpeaker", () => {
  it("treats unlabeled tokens and the room id as the host", () => {
    expect(isRoomHostSpeaker(undefined, "host")).toBe(true);
    expect(isRoomHostSpeaker("host", "host")).toBe(true);
    expect(isRoomHostSpeaker("doctor", "host")).toBe(false);
  });
});

describe("groupConsecutiveAssistantMessages", () => {
  it("keeps tool-role rows inside the assistant turn", () => {
    const groups = groupConsecutiveAssistantMessages([
      msg("user", "u1", { content: "hi" }),
      msg("assistant", "a1", {
        toolData: { name: "read_file", arguments: "{}" },
      }),
      msg("tool", "t1", {
        toolData: { name: "read_file", output: "ok" },
      }),
      msg("assistant", "a2", {
        content: "done",
        contentBlocks: [{ type: "thinking", content: "…" }],
      }),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups[0].messages.map((m) => m.id)).toEqual(["u1"]);
    expect(groups[1].isGroup).toBe(true);
    expect(groups[1].messages.map((m) => m.id)).toEqual(["a1", "t1", "a2"]);
  });

  it("splits wrap-up from the host dispatch group", () => {
    const groups = groupConsecutiveAssistantMessages([
      msg("assistant", "host1", { content: "I will ask" }),
      msg("assistant", "wrap", {
        content: "here is the summary",
        teamWrapup: true,
      }),
    ]);
    expect(groups.map((group) => group.messages.map((m) => m.id))).toEqual([
      ["host1"],
      ["wrap"],
    ]);
  });

  it("keeps a 1:1 ask_agent turn in one group", () => {
    const groups = groupConsecutiveAssistantMessages([
      msg("assistant", "host1", { content: "I will ask" }),
      msg("assistant", "tool", {
        toolData: { name: "ask_agent", arguments: "{}", output: "queued" },
      }),
      msg("assistant", "host2", { content: "here is the summary" }),
    ]);
    expect(groups.map((group) => group.messages.map((m) => m.id))).toEqual([
      ["host1", "tool", "host2"],
    ]);
  });

  it("keeps unlabeled and host-stamped rows together in a 1:1 room", () => {
    const groups = groupConsecutiveAssistantMessages(
      [
        msg("assistant", "a1", { content: "first" }),
        msg("assistant", "a2", {
          content: "second",
          speakerAgentId: "C9EBEC",
        }),
      ],
      "C9EBEC",
    );
    expect(groups.map((group) => group.messages.map((m) => m.id))).toEqual([
      ["a1", "a2"],
    ]);
  });

  it("splits consecutive assistants when the team speaker changes", () => {
    const groups = groupConsecutiveAssistantMessages([
      msg("user", "u1", { content: "ask the doctor" }),
      msg("assistant", "host1", { content: "I will ask" }),
      msg("assistant", "member1", {
        content: "take rest",
        speakerAgentId: "doctor",
      }),
      msg("assistant", "host2", {
        content: "here is the summary",
        speakerAgentId: "host",
      }),
    ]);
    expect(groups.map((group) => group.messages.map((m) => m.id))).toEqual([
      ["u1"],
      ["host1"],
      ["member1"],
      ["host2"],
    ]);
  });

  it("continues the speaker text bubble even if it is not last", () => {
    const messages = [
      msg("assistant", "host", { content: "I will ask" }),
      msg("assistant", "member", {
        content: "please ",
        speakerAgentId: "doctor",
        status: "done",
      }),
    ];
    expect(findSpeakerTextToContinue(messages, "doctor")).toBe(1);
    expect(findSpeakerTextToContinue(messages, undefined)).toBe(0);
  });

  it("walks past another speaker instead of opening a new bubble", () => {
    const messages = [
      msg("assistant", "host1", { content: "I" }),
      msg("assistant", "member1", {
        content: "please",
        speakerAgentId: "doctor",
      }),
      msg("assistant", "host2", { content: " will" }),
      msg("assistant", "member2", {
        content: " rest",
        speakerAgentId: "doctor",
      }),
    ];
    expect(findSpeakerTextToContinue(messages, undefined)).toBe(2);
    expect(findSpeakerTextToContinue(messages, "doctor")).toBe(3);
  });

  it("still starts a new bubble after this speaker's own tool", () => {
    const messages = [
      msg("assistant", "host", { content: "I will ask" }),
      msg("assistant", "tool", {
        toolData: { name: "ask_agent", arguments: "{}" },
      }),
      msg("assistant", "member", {
        content: "please",
        speakerAgentId: "doctor",
      }),
    ];
    expect(findSpeakerTextToContinue(messages, undefined)).toBe(-1);
    expect(findSpeakerTextToContinue(messages, "doctor")).toBe(2);
    expect(
      findSpeakerTextToContinue(messages, undefined, undefined, {
        continueThroughTools: ["ask_agent"],
      }),
    ).toBe(0);
  });

  it("treats a completed ask_agent as a turn break", () => {
    const messages = [
      msg("assistant", "host", { content: "I will ask" }),
      msg("assistant", "tool", {
        toolData: { name: "ask_agent", arguments: "{}", output: "queued" },
      }),
      msg("assistant", "member", {
        content: "please",
        speakerAgentId: "doctor",
      }),
    ];
    expect(
      findSpeakerTextToContinue(messages, undefined, undefined, {
        continueThroughTools: ["ask_agent"],
      }),
    ).toBe(-1);
    expect(speakerTurnWasInterrupted(messages, 0, undefined)).toBe(true);
  });

  it("does not resume a prior turn after a user message", () => {
    const messages = [
      msg("assistant", "old", { content: "before" }),
      msg("user", "u1", { content: "again" }),
      msg("assistant", "member", {
        content: "please",
        speakerAgentId: "doctor",
      }),
    ];
    expect(findSpeakerTextToContinue(messages, undefined)).toBe(-1);
    expect(findSpeakerTextToContinue(messages, "doctor")).toBe(2);
  });

  it("does not continue a stamped host bubble from an unlabeled token", () => {
    const messages = [
      msg("assistant", "host", {
        content: "I will ask",
        speakerAgentId: "host",
      }),
      msg("assistant", "member", {
        content: "please",
        speakerAgentId: "doctor",
      }),
    ];
    expect(
      findSpeakerTextToContinue(messages, undefined, "host", {
        teamRoom: true,
      }),
    ).toBe(-1);
    expect(findSpeakerTextToContinue(messages, "host", "host")).toBe(0);
    expect(findSpeakerTextToContinue(messages, "doctor", "host")).toBe(1);
  });

  it("continues a stamped 1:1 host bubble from an unlabeled token", () => {
    const messages = [
      msg("assistant", "host", {
        content: "Hello",
        speakerAgentId: "C9EBEC",
      }),
    ];
    expect(findSpeakerTextToContinue(messages, undefined, "C9EBEC")).toBe(0);
  });

  it("merges split member texts into one answer bubble", () => {
    const split = splitAssistantTurn([
      msg("assistant", "m1", {
        content: "please ",
        speakerAgentId: "doctor",
      }),
      msg("assistant", "m2", {
        content: "rest",
        speakerAgentId: "doctor",
      }),
    ]);
    expect(split.answerMessage?.content).toBe("please rest");
  });

  it("keeps a 1:1 ReAct conclusion as the answer", () => {
    const split = splitAssistantTurn([
      msg("assistant", "host1", { content: "I will ask" }),
      msg("assistant", "tool", {
        toolData: { name: "ask_agent", arguments: "{}", output: "queued" },
      }),
      msg("assistant", "host2", { content: "here is the summary" }),
    ]);
    expect(split.answerMessage?.content).toBe("here is the summary");
  });

  it("does not join an identical host dispatch twice", () => {
    const split = splitAssistantTurn([
      msg("assistant", "h1", {
        content: "已安排临床助手为您整理心脏病的治疗方案，稍等片刻。",
        speakerAgentId: "host",
      }),
      msg("assistant", "h2", {
        content: "已安排临床助手为您整理心脏病的治疗方案，稍等片刻。",
        speakerAgentId: "host",
      }),
    ]);
    expect(split.answerMessage?.content).toBe(
      "已安排临床助手为您整理心脏病的治疗方案，稍等片刻。",
    );
  });

  it("still splits on user messages", () => {
    const groups = groupConsecutiveAssistantMessages([
      msg("assistant", "a1", { content: "one" }),
      msg("user", "u1", { content: "again" }),
      msg("assistant", "a2", { content: "two" }),
    ]);
    expect(groups).toHaveLength(3);
    expect(groups[1].messages[0].id).toBe("u1");
  });
});
