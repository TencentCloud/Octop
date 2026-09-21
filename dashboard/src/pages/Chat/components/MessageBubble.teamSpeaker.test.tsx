import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessageBubble from "./MessageBubble";
import type { ChatMessage } from "../hooks/useChat";
import { ChatAgentProfileProvider } from "../ChatAgentProfileContext";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { name?: string }) =>
      key === "chat.teamHostHover" ? `[${opts?.name ?? ""}] 主持人` : key,
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
      {
        agent_id: "doctor",
        name: "小通 · 通用助手",
        icon_name: "sparkles",
      },
    ],
  }),
}));

function assistant(extra: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: extra.id ?? "m1",
    role: "assistant",
    content: extra.content ?? "please rest",
    status: "done",
    timestamp: Date.now(),
    ...extra,
  };
}

describe("MessageBubble team speaker chrome", () => {
  it("does not print the member name next to the bubble", () => {
    render(
      <MessageBubble
        message={assistant({ speakerAgentId: "doctor" })}
        agentId="host"
        showAvatar
        groupPosition="only"
      />,
    );

    expect(screen.getByText("please rest")).toBeInTheDocument();
    expect(screen.queryByText("小通 · 通用助手")).not.toBeInTheDocument();
  });

  it("labels the host avatar as team host and opens a member profile", () => {
    const onOpen = vi.fn();
    const { rerender } = render(
      <ChatAgentProfileProvider canOpen onOpen={onOpen} isTeam>
        <MessageBubble
          message={assistant({ content: "稍等", speakerAgentId: "host" })}
          agentId="host"
          showAvatar
          groupPosition="only"
        />
      </ChatAgentProfileProvider>,
    );
    expect(
      screen.getByRole("button", { name: "[主持团队] 主持人" }),
    ).toBeInTheDocument();

    rerender(
      <ChatAgentProfileProvider canOpen onOpen={onOpen} isTeam>
        <MessageBubble
          message={assistant({ speakerAgentId: "doctor" })}
          agentId="host"
          showAvatar
          groupPosition="only"
        />
      </ChatAgentProfileProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "小通 · 通用助手" }));
    expect(onOpen).toHaveBeenCalledWith("doctor");
  });
});
