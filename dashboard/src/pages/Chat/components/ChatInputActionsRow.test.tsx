import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ResolvedModel } from "../../../api/types";
import ChatInputActionsRow from "./ChatInputActionsRow";

// `isSttAvailable()` runs at module load, so the browser APIs it probes must
// exist before this module graph is imported.
vi.hoisted(() => {
  vi.stubGlobal("MediaRecorder", class {});
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: () => Promise.resolve() },
    configurable: true,
  });
  return true;
});

vi.mock("./ContextWindowRing", () => ({
  default: () => <div data-testid="context-window-ring" />,
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
  onFolderSelect: vi.fn(),
  onNewChat: vi.fn(),
  onPolish: vi.fn(),
  onToggleVoice: vi.fn(),
  onCancel: vi.fn(),
  onSubmit: vi.fn(),
};

describe("ChatInputActionsRow plus menu", () => {
  it("keeps approval, shortcuts, and attachments on the toolbar", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("composer-plus")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Model")).toBeInTheDocument();
    expect(
      screen.getByLabelText("chat.conversationMode.picker"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("hitl-policy-picker")).toBeInTheDocument();
    expect(screen.getByLabelText("快捷指令")).toBeInTheDocument();
    expect(screen.getByLabelText("Upload")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Folder" })).toBeNull();
    expect(
      screen.queryByTestId("conversation-mode-picker"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("conversation-mode-hint"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("context-window-ring")).toBeInTheDocument();
  });

  it("hides context usage for a managed expert", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} managed />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("context-window-ring")).not.toBeInTheDocument();
    expect(screen.getByTestId("managed-approval-picker")).toBeInTheDocument();
    expect(screen.queryByTestId("hitl-policy-picker")).not.toBeInTheDocument();
  });

  it("keeps approval when the managed agent has no unattended mode", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          managed
          sessionMode="build"
          onSessionModeChange={() => undefined}
          sessionModes={[
            {
              id: "build",
              name_zh: "构建",
              name_en: "Build",
              hint_zh: "",
              hint_en: "",
            },
            {
              id: "plan",
              name_zh: "规划",
              name_en: "Plan",
              hint_zh: "",
              hint_en: "",
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("managed-approval-picker")).toBeInTheDocument();
    expect(
      screen.getByLabelText("chat.conversationMode.picker"),
    ).toBeInTheDocument();
  });

  it("hides approval when a session mode already skips it", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          managed
          sessionMode="default"
          onSessionModeChange={() => undefined}
          sessionModes={[
            {
              id: "default",
              name_zh: "默认",
              name_en: "Default",
              hint_zh: "",
              hint_en: "",
            },
            {
              id: "bypassPermissions",
              name_zh: "YOLO",
              name_en: "YOLO",
              hint_zh: "",
              hint_en: "",
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(
      screen.queryByTestId("managed-approval-picker"),
    ).not.toBeInTheDocument();
  });

  it("keeps connector and knowledge pickers for a managed expert", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          managed
          availableConnectors={[
            { mcp_server_name: "notes", label: "Notes", kind: "custom" },
          ]}
          selectedConnectors={[]}
          onConnectorsChange={() => undefined}
          availableKnowledgeBases={[
            {
              id: "kb1",
              owner_user_id: 1,
              name: "手册",
              description: "",
              default_open: false,
              shared: false,
              icon_name: "book",
              embedding_model: "",
              embedding_dim: 0,
              doc_count: 0,
              max_documents: 1,
              created_at: 0,
              updated_at: 0,
            },
          ]}
          selectedKnowledgeBaseIds={[]}
          onKnowledgeBaseIdsChange={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText("connectors.chatPicker")).toBeInTheDocument();
    expect(screen.getByLabelText("chat.knowledgePicker")).toBeInTheDocument();
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument();
  });

  it("keeps the expert picker for a managed expert", () => {
    render(
      <MemoryRouter>
        <ChatInputActionsRow
          {...baseProps}
          managed
          availableExperts={[
            {
              agent_id: "other",
              name: "分析师",
              description: "",
              avatar_url: null,
              kind: "expert",
            },
          ]}
          onInsertExpertMention={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText("chat.expertPicker")).toBeInTheDocument();
  });

  it("folds shortcut, upload, and polish into the plus menu when the composer is narrow", async () => {
    const rect = {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 40,
      right: 360,
      width: 360,
      height: 40,
      toJSON: () => ({}),
    } as DOMRect;
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockReturnValue(rect);
    const OriginalObserver = globalThis.ResizeObserver;
    class NarrowObserver {
      private readonly callback: ResizeObserverCallback;

      constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
      }

      observe() {
        this.callback(
          [{ contentRect: { width: 360, height: 40 } } as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        );
      }

      unobserve() {}

      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", NarrowObserver);
    try {
      const onFileSelect = vi.fn();
      render(
        <MemoryRouter>
          <ChatInputActionsRow {...baseProps} onFileSelect={onFileSelect} />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.queryByLabelText("快捷指令")).not.toBeInTheDocument();
      });
      expect(screen.queryByLabelText("Upload")).not.toBeInTheDocument();
      expect(screen.getByTestId("hitl-policy-picker")).toBeInTheDocument();
      expect(
        screen.queryByTestId("conversation-mode-hint"),
      ).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId("composer-plus"));
      expect(
        await screen.findByText("chat.polish.tooltip"),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByText("Upload"));
      fireEvent.click(await screen.findByRole("menuitem", { name: "Files" }));
      expect(onFileSelect).toHaveBeenCalledTimes(1);
    } finally {
      rectSpy.mockRestore();
      vi.stubGlobal("ResizeObserver", OriginalObserver);
    }
  });

  it("starts a folder upload from the toolbar", () => {
    const onFolderSelect = vi.fn();
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} onFolderSelect={onFolderSelect} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText("Upload"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Folder" }));
    expect(onFolderSelect).toHaveBeenCalledTimes(1);
  });

  it("starts a file upload from the same menu", () => {
    const onFileSelect = vi.fn();
    render(
      <MemoryRouter>
        <ChatInputActionsRow {...baseProps} onFileSelect={onFileSelect} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText("Upload"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Files" }));
    expect(onFileSelect).toHaveBeenCalledTimes(1);
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
        <ChatInputActionsRow
          {...baseProps}
          availableConnectors={[]}
          onConnectorsChange={vi.fn()}
        />
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
        <ChatInputActionsRow
          {...baseProps}
          availableModels={extraModels}
          availableConnectors={[]}
          onConnectorsChange={vi.fn()}
        />
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

function renderRow(overrides: Record<string, unknown> = {}) {
  const handlers = {
    onVoiceStart: vi.fn(),
    onVoiceStop: vi.fn(),
    onToggleVoice: vi.fn(),
  };
  const view = render(
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
        slashPickerGroups={null}
        slashMenuItems={[]}
        onSlashShortcutSelect={vi.fn()}
        onFileSelect={vi.fn()}
        onNewChat={vi.fn()}
        onPolish={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
        {...handlers}
        {...overrides}
      />
    </MemoryRouter>,
  );
  const mic = view.container
    .querySelector("svg.lucide-mic")
    ?.closest("button") as HTMLButtonElement;
  return { ...view, ...handlers, mic };
}

describe("ChatInputActionsRow voice button", () => {
  it("dictates while held down when realtime STT is on", () => {
    const { mic, onVoiceStart, onVoiceStop, onToggleVoice } = renderRow({
      voiceHoldToTalk: true,
    });

    fireEvent.pointerDown(mic);
    expect(onVoiceStart).toHaveBeenCalledTimes(1);

    fireEvent.pointerUp(mic);
    expect(onVoiceStop).toHaveBeenCalledTimes(1);

    // A plain click must not toggle the recorder in hold-to-talk mode.
    fireEvent.click(mic);
    expect(onToggleVoice).not.toHaveBeenCalled();
    expect(onVoiceStart).toHaveBeenCalledTimes(1);
  });

  it("finishes when the pointer slides off the button", () => {
    const { mic, onVoiceStop } = renderRow({ voiceHoldToTalk: true });

    fireEvent.pointerDown(mic);
    fireEvent.pointerLeave(mic);
    fireEvent.pointerUp(mic);

    expect(onVoiceStop).toHaveBeenCalledTimes(1);
  });

  it("keeps click-to-toggle when realtime STT is off", () => {
    const { mic, onToggleVoice, onVoiceStart } = renderRow();

    fireEvent.click(mic);
    expect(onToggleVoice).toHaveBeenCalledTimes(1);

    fireEvent.pointerDown(mic);
    expect(onVoiceStart).not.toHaveBeenCalled();
  });

  it("stays available while a reply is still streaming", () => {
    const { mic } = renderRow({ voiceHoldToTalk: true, isStreaming: true });

    expect(mic).not.toBeDisabled();
  });
});
