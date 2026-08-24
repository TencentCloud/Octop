import { fireEvent, render, waitFor } from "@testing-library/react";
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

describe("ChatInputActionsRow compact pickers", () => {
  it("uses a popover instead of a full-width drawer on narrow desktop", async () => {
    const { container } = render(
      <ChatInputActionsRow
        isMobile={false}
        isStreaming={false}
        canSend={false}
        text=""
        polishing={false}
        uploading={false}
        recording={false}
        transcribing={false}
        availableModels={models}
        onModelChange={vi.fn()}
        slashPickerGroups={null}
        slashMenuItems={[]}
        onSlashShortcutSelect={vi.fn()}
        onFileSelect={vi.fn()}
        onNewChat={vi.fn()}
        onPolish={vi.fn()}
        onToggleVoice={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
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
