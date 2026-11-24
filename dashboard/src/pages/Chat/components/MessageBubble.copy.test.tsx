import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessageBubble from "./MessageBubble";
import type { ChatMessage } from "../hooks/useChat";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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
    activeAgent: { agent_id: "a1", name: "Helper", icon_name: "bot" },
    agents: [{ agent_id: "a1", name: "Helper", icon_name: "bot" }],
  }),
}));

function reply(content: string): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    content,
    status: "done",
    timestamp: Date.now(),
  };
}

describe("MessageBubble copy action on assistant replies", () => {
  it("offers Copy on a reply that has nothing to read aloud", () => {
    render(
      <MessageBubble message={reply("```sh\nls -la\n```")} agentId="a1" />,
    );
    expect(screen.getByRole("button", { name: "common.copy" })).toBeTruthy();
    expect(screen.queryByTitle("voice.readAloud")).toBeNull();
  });

  it("offers Copy when read-aloud is turned off", () => {
    render(
      <MessageBubble
        message={reply("A plain answer.")}
        agentId="a1"
        readAloud={false}
      />,
    );
    expect(screen.getByRole("button", { name: "common.copy" })).toBeTruthy();
    expect(screen.queryByTitle("voice.readAloud")).toBeNull();
  });

  it("keeps Copy next to read-aloud on a normal reply", () => {
    render(<MessageBubble message={reply("A plain answer.")} agentId="a1" />);
    expect(screen.getByRole("button", { name: "common.copy" })).toBeTruthy();
    expect(screen.getByTitle("voice.readAloud")).toBeTruthy();
  });
});
