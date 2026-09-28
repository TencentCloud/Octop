import { fireEvent, render, screen } from "@testing-library/react";
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

const userMessage: ChatMessage = {
  id: "u1",
  role: "user",
  content: "旧的问题",
  status: "done",
  timestamp: Date.now(),
};

function openEditor(onEditUserMessage: (id: string, text: string) => void) {
  render(
    <MessageBubble
      message={userMessage}
      agentId="a1"
      onEditUserMessage={onEditUserMessage}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
  const textarea = screen.getByRole("textbox");
  fireEvent.change(textarea, { target: { value: "新的问题 xin" } });
  return textarea;
}

describe("MessageBubble edit and resend with an input method", () => {
  it("does not resend on the Enter that confirms an IME candidate", () => {
    const onEdit = vi.fn();
    const textarea = openEditor(onEdit);

    fireEvent.keyDown(textarea, { key: "Enter", isComposing: true });
    fireEvent.keyDown(textarea, { key: "Enter", keyCode: 229 });

    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toHaveValue("新的问题 xin");
  });

  it("keeps the edit open when Escape only closes the IME candidates", () => {
    const onEdit = vi.fn();
    const textarea = openEditor(onEdit);

    fireEvent.keyDown(textarea, { key: "Escape", keyCode: 229 });

    expect(screen.getByRole("textbox")).toHaveValue("新的问题 xin");
  });

  it("still resends on a plain Enter", () => {
    const onEdit = vi.fn();
    const textarea = openEditor(onEdit);

    fireEvent.keyDown(textarea, { key: "Enter", keyCode: 13 });

    expect(onEdit).toHaveBeenCalledWith("u1", "新的问题 xin");
  });
});
