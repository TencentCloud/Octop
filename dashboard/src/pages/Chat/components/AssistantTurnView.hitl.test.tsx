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
  it("seals the process panel when the turn ends despite stale message flags", () => {
    const messages = [
      message({
        id: "tool",
        status: "streaming",
        toolData: { name: "read_file", arguments: "{}", output: "ok" },
      }),
      message({ id: "answer", content: "Completed answer" }),
    ];
    const { rerender } = render(
      <AssistantTurnView messages={messages} isTurnInProgress />,
    );
    expect(screen.getByText("整理结果中")).toBeInTheDocument();
    rerender(
      <AssistantTurnView messages={messages} isTurnInProgress={false} />,
    );
    expect(screen.queryByText("整理结果中")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /已调用/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByText("Completed answer")).toBeInTheDocument();
  });

  it("keeps a current team member live after the host finishes", () => {
    render(
      <AssistantTurnView
        messages={[
          message({
            id: "member-tool",
            speakerAgentId: "member",
            toolData: { name: "read_file", arguments: "{}", output: "ok" },
          }),
        ]}
        isTurnInProgress={false}
        liveSpeakers={["member"]}
      />,
    );
    expect(screen.getByText("整理结果中")).toBeInTheDocument();
  });

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
});
