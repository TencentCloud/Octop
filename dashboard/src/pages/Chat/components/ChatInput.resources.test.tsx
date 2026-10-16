import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../../../hooks/useIsMobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("../../../hooks/useSlashCommands", () => ({
  useSlashCommands: () => ({
    commands: [],
    labelFor: (cmd: string) => cmd,
  }),
}));

vi.mock("../../../hooks/useVoiceInput", () => ({
  useVoiceInput: () => ({
    recording: false,
    transcribing: false,
    realtime: false,
    start: vi.fn(),
    stop: vi.fn(),
    toggle: vi.fn(),
  }),
}));

vi.mock("../../../hooks/useKeepInVisualViewport", () => ({
  useKeepInVisualViewport: () => undefined,
}));

vi.mock("../../../hooks/viewport", () => ({
  isPwaDisplay: () => false,
  needsComposerVisualViewportFix: () => false,
}));

vi.mock("../hooks/useChatAttachments", () => ({
  useChatAttachments: () => ({
    attachments: [],
    uploading: false,
    dragOver: false,
    fileInputRef: { current: null },
    folderInputRef: { current: null },
    handleFileSelect: vi.fn(),
    handleFolderSelect: vi.fn(),
    handleFileChange: vi.fn(),
    removeAttachment: vi.fn(),
    clearAttachments: vi.fn(),
    restoreAttachments: vi.fn(),
    handlePaste: vi.fn(),
    handleDragEnter: vi.fn(),
    handleDragLeave: vi.fn(),
    handleDragOver: vi.fn(),
    handleDrop: vi.fn(),
  }),
}));

vi.mock("../hooks/chatStore", () => ({
  onSteerRestore: () => () => {},
  consumePendingPrefillAttachments: () => [],
  readInputDraft: (agentId: string) =>
    agentId === "agent-2" ? "target expert draft" : "",
  writeInputDraft: vi.fn(),
}));

vi.mock("./ChatInputPreviewBar", () => ({
  default: ({ selectedConnectors }: { selectedConnectors: string[] }) => (
    <div data-testid="connector-preview">{selectedConnectors.join(",")}</div>
  ),
}));

vi.mock("./ChatInputActionsRow", () => ({
  default: ({
    onSubmit,
    canSend,
  }: {
    onSubmit: () => void;
    canSend: boolean;
  }) => (
    <button type="button" disabled={!canSend} onClick={onSubmit}>
      send
    </button>
  ),
}));

vi.mock("./ChatQueuedMessages", () => ({
  default: () => null,
}));

vi.mock("./SlashCommandMenu", () => ({
  default: () => null,
}));

vi.mock("./MentionPickerMenu", () => ({
  default: () => null,
  buildMentionItems: () => [],
}));

vi.mock("../hooks/useSlashMentionInput", () => ({
  useSlashMentionInput: ({
    text,
    setText,
    onSubmitRef,
  }: {
    text: string;
    setText: (v: string) => void;
    onSubmitRef: { current: () => void };
  }) => ({
    slashMenuOpen: false,
    slashMenuIndex: 0,
    setSlashMenuIndex: vi.fn(),
    mentionMenuOpen: false,
    mentionMenuIndex: 0,
    setMentionMenuIndex: vi.fn(),
    mentionQuery: "",
    mentionAgents: [],
    slashMenuFlat: [],
    slashMenuGroups: [],
    slashPickerGroups: [],
    slashMenuItems: [],
    mentionItems: [],
    filesLoading: false,
    filesError: null,
    runSlashCommand: vi.fn(),
    matchSlashCommand: () => null,
    handleMentionSelect: vi.fn(),
    handleSlashSelect: vi.fn(),
    handleTextChange: setText,
    handleKeyDown: (e: { key: string; preventDefault: () => void }) => {
      if (e.key === "Enter" && !e.preventDefault) return;
      void text;
      void onSubmitRef;
    },
  }),
}));

import ChatInput from "./ChatInput";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ChatInput effective connector preview", () => {
  it.each(["ask", "plan"] as const)(
    "hides unused connectors in %s and restores them in Craft",
    (mode) => {
      const onConnectorsChange = vi.fn();
      const props = {
        onSend: vi.fn(),
        onCancel: vi.fn(),
        onNewChat: vi.fn(),
        isStreaming: false,
        agentId: "expertA",
        selectedConnectors: ["c1"],
        onConnectorsChange,
      };
      const { rerender } = render(
        <ChatInput {...props} conversationMode={mode} />,
      );
      expect(screen.getByTestId("connector-preview")).toBeEmptyDOMElement();
      rerender(<ChatInput {...props} conversationMode="craft" />);
      expect(screen.getByTestId("connector-preview")).toHaveTextContent("c1");
      rerender(<ChatInput {...props} conversationMode={mode} />);
      expect(screen.getByTestId("connector-preview")).toBeEmptyDOMElement();
      expect(onConnectorsChange).not.toHaveBeenCalled();
    },
  );
});
