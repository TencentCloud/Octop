import { fireEvent, render, waitFor, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ResolvedModel } from "../../../api/types";
import ChatInputActionsRow from "./ChatInputActionsRow";

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
  slashPickerGroups: null as null,
  slashMenuItems: [] as [],
  onSlashShortcutSelect: vi.fn(),
  onFileSelect: vi.fn(),
  onNewChat: vi.fn(),
  onPolish: vi.fn(),
  onToggleVoice: vi.fn(),
  onCancel: vi.fn(),
  onSubmit: vi.fn(),
};

function renderRow(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("ChatInputActionsRow compact pickers", () => {
  it("uses a popover instead of a full-width drawer on narrow desktop", async () => {
    const { container } = renderRow(
      <ChatInputActionsRow
        {...baseProps}
        availableModels={models}
        onModelChange={vi.fn()}
      />,
    );

    const modelButton = container
      .querySelector("svg.lucide-cpu")
      ?.closest("button");
    expect(modelButton).not.toBeNull();

    fireEvent.click(modelButton!);

    await waitFor(() => {
      expect(document.querySelector(".ant-popover")).toBeInTheDocument();
    });
    expect(document.querySelector(".ant-drawer-content")).toBeNull();
  });
});

describe("ChatInputActionsRow conversation mode (#616 M13)", () => {
  it("shows status + Default/Plan/Ask labels and notifies on Ask select", async () => {
    const onConversationModeChange = vi.fn();
    renderRow(
      <ChatInputActionsRow
        {...baseProps}
        conversationMode="craft"
        onConversationModeChange={onConversationModeChange}
      />,
    );

    fireEvent.click(screen.getByTestId("conversation-mode-trigger"));

    await waitFor(() => {
      expect(
        screen.getAllByTestId("conversation-mode-menu").length,
      ).toBeGreaterThan(0);
    });
    const menu = screen.getAllByTestId("conversation-mode-menu")[0]!;
    expect(menu).toHaveTextContent("当前为默认模式");
    expect(menu).toHaveTextContent("默认");
    expect(menu).toHaveTextContent("计划");
    expect(menu).toHaveTextContent("仅问答");

    fireEvent.click(screen.getAllByTestId("conversation-mode-option-ask")[0]!);
    expect(onConversationModeChange).toHaveBeenCalledWith("ask");
  });
});
