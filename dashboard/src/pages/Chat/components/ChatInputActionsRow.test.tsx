import { fireEvent, render, waitFor, within } from "@testing-library/react";
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

describe("ChatInputActionsRow compact pickers", () => {
  it("uses a popover instead of a full-width drawer on narrow desktop", async () => {
    const { container } = render(
      <MemoryRouter>
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
        />
      </MemoryRouter>,
    );

    const modelButton = container
      .querySelector("svg.lucide-cpu")
      ?.closest("button");
    expect(modelButton).not.toBeNull();
    expect(modelButton).not.toHaveTextContent("Auto");
    expect(modelButton).not.toHaveTextContent("Compact Model");
    expect(modelButton).not.toHaveTextContent("compact-model");

    fireEvent.click(modelButton!);

    // Retryable + icon-agnostic anchor: the model menu's "Auto" entry (role and
    // accessible name) plus the provider icon. The Auto entry's icon was changed
    // from `lucide-sparkles` to `lucide-route` in c7f82867, so pinning the icon
    // class re-breaks this test without adding discrimination.
    await waitFor(() => {
      const popover = document.querySelector(".ant-popover");
      expect(popover).not.toBeNull();
      expect(
        within(popover as HTMLElement).getByRole("button", { name: /Auto/ }),
      ).toBeInTheDocument();
      expect(popover?.querySelector("img")).not.toBeNull();
    });
    expect(document.querySelector(".ant-drawer-content")).toBeNull();
  });
});
