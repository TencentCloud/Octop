import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessageBubble from "./MessageBubble";
import type { ChatMessage } from "../hooks/useChat";
import type { OctopUser } from "../../../api/modules/auth";

const currentUser: Partial<OctopUser> = {
  username: "ada",
  display_name: "Ada",
  avatar_icon: "business",
  avatar_url: null,
};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => currentUser,
}));

vi.mock("../../../hooks/useAuthImageSrc", () => ({
  useAuthImageSrc: (url: string) => ({
    src: url || "",
    loadState: url ? "ready" : "idle",
  }),
}));

vi.mock("../../../context/VoiceOutputContext", () => ({
  useVoiceOutputContext: () => ({ speakingId: null, speak: vi.fn() }),
}));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({
    activeAgent: { agent_id: "host", name: "助手", icon_name: "bot" },
    agents: [],
  }),
}));

function userMessage(extra: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: extra.id ?? "u1",
    role: "user",
    content: extra.content ?? "hello there",
    status: "done",
    timestamp: Date.now(),
    ...extra,
  };
}

describe("MessageBubble user avatar", () => {
  it("shows the account preset icon instead of name initials", () => {
    currentUser.avatar_icon = "business";
    currentUser.avatar_url = null;
    render(<MessageBubble message={userMessage()} showAvatar />);

    const sender = screen.getByLabelText("Ada");
    expect(sender.querySelector("svg")).toBeTruthy();
    expect(sender).not.toHaveTextContent("A");
  });

  it("shows the uploaded account photo when present", () => {
    currentUser.avatar_icon = "user";
    currentUser.avatar_url = "/api/users/7/avatar";
    render(<MessageBubble message={userMessage()} showAvatar />);

    const sender = screen.getByLabelText("Ada");
    expect(sender.querySelector("img")).toHaveAttribute(
      "src",
      "/api/users/7/avatar",
    );
    expect(sender.querySelector("svg")).toBeNull();
  });
});
