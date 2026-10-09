import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

beforeEach(() => vi.clearAllMocks());

describe("ChatInputActionsRow plus menu", () => {
  it("keeps the follow-default entry searchable by its model name", async () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          defaultModel="Provider/compact-model"
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("composer-plus"));
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Model Default: Compact Model",
      }),
    );
    fireEvent.change(screen.getByPlaceholderText("Search models"), {
      target: { value: "compact" },
    });
    const defaultEntry = screen.getByRole("button", {
      name: "Default: Compact Model Use agent default: Provider / Compact Model",
    });
    expect(defaultEntry).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Provider / Compact Model",
        exact: true,
      }),
    ).toBeInTheDocument();
    fireEvent.click(defaultEntry);
    expect(baseProps.onModelChange).toHaveBeenCalledWith(null);
  });

  it("follows default model changes without setting an explicit model override", async () => {
    const { rerender } = render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          defaultModel="Provider/compact-model"
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("composer-plus"));
    const trigger = await screen.findByRole("button", {
      name: "Model Default: Compact Model",
    });
    fireEvent.click(trigger);
    const followDefault = await screen.findByRole("button", {
      name: "Default: Compact Model Use agent default: Provider / Compact Model",
    });
    expect(baseProps.onModelChange).not.toHaveBeenCalled();
    fireEvent.click(followDefault);
    expect(baseProps.onModelChange).toHaveBeenCalledWith(null);
    rerender(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} defaultModel="Other/new-model" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("composer-plus"));
    expect(
      await screen.findByRole("button", { name: "Model Default: new-model" }),
    ).toBeInTheDocument();
  });

  it("keeps an explicit model selection visible instead of the expert default", async () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          selectedModel="Provider/compact-model"
          defaultModel="Other/new-model"
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("composer-plus"));
    expect(
      await screen.findByRole("button", {
        name: "Model Provider / Compact Model",
      }),
    ).toBeInTheDocument();
  });

  it.each(["ask", "plan"] as const)(
    "counts only KBs in %s and restores selected resources in Craft",
    (mode) => {
      const props = {
        ...baseProps,
        selectedConnectors: ["c1"],
        selectedKnowledgeBaseIds: ["k1"],
        text: "/skill",
      };
      const { rerender } = render(
        <MemoryRouter>
          <ChatInputActionsRow {...props} conversationMode={mode} />
        </MemoryRouter>,
      );
      expect(screen.getByTestId("composer-plus")).toHaveTextContent("1");
      rerender(
        <MemoryRouter>
          <ChatInputActionsRow {...props} conversationMode="craft" />
        </MemoryRouter>,
      );
      expect(screen.getByTestId("composer-plus")).toHaveTextContent("3");
      rerender(
        <MemoryRouter>
          <ChatInputActionsRow {...props} conversationMode={mode} />
        </MemoryRouter>,
      );
      expect(screen.getByTestId("composer-plus")).toHaveTextContent("1");
    },
  );

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
    expect(
      screen.queryByTestId("conversation-mode-hint"),
    ).not.toBeInTheDocument();
  });

  it("shows a non-interactive Ask/Plan reminder in the toolbar gap", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} conversationMode="plan" />
      </MemoryRouter>,
    );

    const hint = screen.getByTestId("conversation-mode-hint");
    expect(hint).toHaveTextContent("chat.conversationMode.planReminder");
    expect(hint.parentElement?.className).not.toMatch(/actionsRowCompact/);
    expect(
      screen.queryByTestId("conversation-mode-picker"),
    ).not.toBeInTheDocument();
  });

  it("keeps the Ask/Plan reminder on mobile without a toolbar button", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} isMobile conversationMode="ask" />
      </MemoryRouter>,
    );

    const hint = screen.getByTestId("conversation-mode-hint");
    expect(hint).toHaveTextContent("chat.conversationMode.askReminder");
    expect(hint.parentElement?.className).toMatch(/actionsRowCompact/);
    expect(
      screen.queryByTestId("conversation-mode-picker"),
    ).not.toBeInTheDocument();
  });

  it("hides the approval picker when HITL policy cannot be changed", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} onHitlPolicyChange={undefined} />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("hitl-policy-picker")).not.toBeInTheDocument();
    expect(screen.getByLabelText("快捷指令")).toBeInTheDocument();
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
    expect(panel.getAttribute("data-align")).toMatch(/^(top|bottom)$/);
    expect(panel.querySelector("img")).not.toBeNull();
    const menu = document.querySelector("[class*='plusFlyoutMenu']");
    if (menu && menu.getBoundingClientRect().height > 0) {
      expect(
        Number.parseFloat(getComputedStyle(panel).maxHeight),
      ).toBeGreaterThanOrEqual(Math.round(menu.getBoundingClientRect().height));
    }
    expect(document.querySelector(".ant-drawer-content")).toBeNull();
    expect(document.querySelector(".ant-popover")).toBeInTheDocument();
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search models")).toBeInTheDocument();
  });

  it("filters models from the plus-menu search box", async () => {
    const extraModels: ResolvedModel[] = [
      ...models,
      {
        provider_id: 2,
        provider_name: "Other",
        provider_kind: "openai",
        model: "other-model",
        name: "Other Model",
        context_window: 128_000,
      },
    ];
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} availableModels={extraModels} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("composer-plus"));
    fireEvent.click(await screen.findByText("Model"));
    expect(
      await screen.findByText("Provider / Compact Model"),
    ).toBeInTheDocument();
    expect(screen.getByText("Other / Other Model")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search models"), {
      target: { value: "compact" },
    });
    expect(screen.getByText("Provider / Compact Model")).toBeInTheDocument();
    expect(screen.queryByText("Other / Other Model")).not.toBeInTheDocument();
  });

  it("shows a search box in the skill picker", async () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          availableSkills={[
            {
              slug: "demo",
              name: "Demo skill",
              description: "A demo skill",
              enabled: true,
              kind: "builtin",
            },
          ]}
          onInsertSkillCommand={vi.fn()}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("composer-plus"));
    fireEvent.click(await screen.findByText("chat.skillPicker"));
    expect(
      await screen.findByPlaceholderText("Search skills"),
    ).toBeInTheDocument();
  });
});
