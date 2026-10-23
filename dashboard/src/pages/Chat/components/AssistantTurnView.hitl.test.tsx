import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../hooks/useChat";
import AssistantTurnView from "./AssistantTurnView";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: string | { defaultValue?: string }) => {
      if (typeof opts === "string") return opts;
      return opts?.defaultValue ?? key;
    },
  }),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ username: "ada", display_name: "Ada" }),
}));

vi.mock("../../../context/VoiceOutputContext", () => ({
  useVoiceOutputContext: () => ({ speakingId: null, speak: vi.fn() }),
}));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({
    activeAgentId: "host",
    activeAgent: {
      agent_id: "host",
      name: "主持团队",
      kind: "team",
      icon_name: "bot",
    },
    agents: [
      {
        agent_id: "host",
        name: "主持团队",
        kind: "team",
        icon_name: "bot",
      },
    ],
  }),
}));

function message(
  extra: Partial<ChatMessage> & Pick<ChatMessage, "id">,
): ChatMessage {
  return {
    role: "assistant",
    content: "",
    status: "done",
    timestamp: 1,
    ...extra,
  };
}

describe("AssistantTurnView approval", () => {
  it("keeps the answer that arrived before the approval card", () => {
    render(
      <AssistantTurnView
        messages={[
          message({ id: "text", content: "磁盘还剩 8G" }),
          message({
            id: "tool",
            toolData: { name: "execute", arguments: "{}" },
          }),
          message({
            id: "card",
            hitlData: {
              action_requests: [{ name: "execute", args: { command: "df" } }],
              status: "pending",
            },
          }),
        ]}
      />,
    );

    expect(screen.getByText("磁盘还剩 8G")).toBeInTheDocument();
    expect(screen.getByText("Confirm this action")).toBeInTheDocument();
  });

  it("keeps host wrap-up below the divider and leaves the decision collapsed", () => {
    render(
      <AssistantTurnView
        messages={[
          message({
            id: "wrap",
            content: "今天就到这里",
            teamWrapup: true,
            speakerAgentId: "host",
            decision: {
              model: "laya",
              empty: false,
              parts: [
                { kind: "result", kept: [{ name: "结果充分", score: 0.91 }] },
              ],
            },
          }),
        ]}
      />,
    );

    const badge = screen.getByText("主持人总结");
    const answer = screen.getByText("今天就到这里");
    expect(
      badge.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText(/决策模型/)).toBeInTheDocument();
    expect(screen.queryByText(/结果充分/)).not.toBeInTheDocument();
  });
});
