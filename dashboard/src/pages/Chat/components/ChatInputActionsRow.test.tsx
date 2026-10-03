import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ResolvedModel } from "../../../api/types";
import ChatInputActionsRow from "./ChatInputActionsRow";
import * as voiceInput from "../../../hooks/useVoiceInput";

vi.mock("./ContextWindowRing", () => ({
  default: () => null,
}));

const models: ResolvedModel[] = [
  {
    provider_id: 1,
    provider_name: "Provider",
    provider_kind: "openai",
    model: "compact-model",
    name: "Compact Model",
    context_window: 128_000,
  },
];

const baseProps = {
  isMobile: false,
  isStreaming: false,
  canSend: false,
  text: "",
  polishing: false,
  uploading: false,
  recording: false,
  transcribing: false,
  availableModels: models,
  onModelChange: vi.fn(),
  onConversationModeChange: vi.fn(),
  onHitlPolicyChange: vi.fn(),
  slashPickerGroups: null,
  slashMenuItems: [],
  onSlashShortcutSelect: vi.fn(),
  onFileSelect: vi.fn(),
  onNewChat: vi.fn(),
  onPolish: vi.fn(),
  onToggleVoice: vi.fn(),
  onCancel: vi.fn(),
  onSubmit: vi.fn(),
};

describe("ChatInputActionsRow plus menu", () => {
  afterEach(() => vi.restoreAllMocks());

  it("explains host-policy blocking on the disabled microphone button", async () => {
    vi.spyOn(voiceInput, "isSttAvailable").mockReturnValue(false);
    vi.spyOn(voiceInput, "isMicrophoneBlockedByPolicy").mockReturnValue(true);
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} />
      </MemoryRouter>,
    );
    const microphone = screen.getByRole("button", {
      name: "voice.startRecording",
    });
    expect(microphone).toBeDisabled();
    fireEvent.mouseEnter(microphone.parentElement!);
    expect(
      await screen.findByText("voice.micBlockedByHost"),
    ).toBeInTheDocument();
  });

  it("keeps approval, shortcuts, and attachments on the toolbar", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("composer-plus")).toBeInTheDocument();
    expect(screen.getByTestId("hitl-policy-picker")).toBeInTheDocument();
    expect(screen.getByLabelText("快捷指令")).toBeInTheDocument();
    expect(screen.getByLabelText("Upload attachment")).toBeInTheDocument();
    expect(
      screen.queryByTestId("conversation-mode-picker"),
    ).not.toBeInTheDocument();
  });

  it("opens a flyout beside the plus menu instead of a window drawer", async () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("composer-plus"));

    await waitFor(() => {
      expect(document.querySelector(".ant-popover")).toBeInTheDocument();
    });
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.queryByTestId("composer-plus-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Model"));

    const panel = await screen.findByTestId("composer-plus-panel");
    expect(panel.querySelector("img")).not.toBeNull();
    const menu = document.querySelector("[class*='plusFlyoutMenu']");
    if (menu && menu.getBoundingClientRect().height > 0) {
      expect(Number.parseFloat(getComputedStyle(panel).maxHeight)).toBe(
        Math.round(menu.getBoundingClientRect().height),
      );
    }
    expect(document.querySelector(".ant-drawer-content")).toBeNull();
    expect(document.querySelector(".ant-popover")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
  });
});
