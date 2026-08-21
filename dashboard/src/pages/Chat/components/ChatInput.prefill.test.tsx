import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { createRef } from "react";

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
    toggle: vi.fn(),
  }),
}));

vi.mock("../../../hooks/useKeyboardOffset", () => ({
  useKeyboardOffset: () => undefined,
}));

vi.mock("../hooks/useChatAttachments", () => ({
  useChatAttachments: () => ({
    attachments: [],
    uploading: false,
    dragOver: false,
    fileInputRef: { current: null },
    handleFileSelect: vi.fn(),
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
  readInputDraft: () => "",
  writeInputDraft: vi.fn(),
}));

vi.mock("./ChatInputPreviewBar", () => ({
  default: () => null,
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

import ChatInput, { type ChatInputHandle } from "./ChatInput";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ChatInput prefill clear-on-send", () => {
  it("does not restore stale initialText after send (skill-card prefill path)", async () => {
    // Mirrors welcome skill/quick-card flow:
    // 1) setPrefillText fills the composer imperatively while parent initialText
    //    is still ""
    // 2) parent keeps the prefill in a ref and re-passes it as initialText on
    //    the next render (e.g. after send updates chat state)
    // 3) composer must stay empty after send — not re-filled from that prop
    const onSend = vi.fn();
    const onCancel = vi.fn();
    const onNewChat = vi.fn();
    const inputRef = createRef<ChatInputHandle>();

    const { rerender } = render(
      <ChatInput
        ref={inputRef}
        onSend={onSend}
        onCancel={onCancel}
        onNewChat={onNewChat}
        isStreaming={false}
        initialText=""
        agentId="agent-1"
        threadId="thread-1"
      />,
    );

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    const prefill = "请填写收件人：";

    act(() => {
      inputRef.current?.setPrefillText(prefill);
    });
    expect(textarea.value).toBe(prefill);

    fireEvent.click(screen.getByRole("button", { name: "send" }));
    expect(onSend).toHaveBeenCalledWith(prefill, undefined);
    expect(textarea.value).toBe("");

    // Parent re-render still holding the prefill string in initialText
    rerender(
      <ChatInput
        ref={inputRef}
        onSend={onSend}
        onCancel={onCancel}
        onNewChat={onNewChat}
        isStreaming={true}
        initialText={prefill}
        agentId="agent-1"
        threadId="thread-1"
      />,
    );

    expect(textarea.value).toBe("");
  });

  it("clears parent prefill via onComposerCleared so edited text cannot be overwritten", () => {
    const onSend = vi.fn();
    const onCancel = vi.fn();
    const onNewChat = vi.fn();
    const inputRef = createRef<ChatInputHandle>();
    let parentPrefill = "";

    const { rerender } = render(
      <ChatInput
        ref={inputRef}
        onSend={onSend}
        onCancel={onCancel}
        onNewChat={onNewChat}
        isStreaming={false}
        initialText=""
        onComposerCleared={() => {
          parentPrefill = "";
        }}
        agentId="agent-1"
        threadId="thread-1"
      />,
    );

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    const prefill = "请填写收件人：";
    parentPrefill = prefill;

    act(() => {
      inputRef.current?.setPrefillText(prefill);
    });
    fireEvent.change(textarea, {
      target: { value: `${prefill}\n张三` },
    });

    fireEvent.click(screen.getByRole("button", { name: "send" }));
    expect(onSend).toHaveBeenCalledWith(`${prefill}\n张三`, undefined);
    expect(textarea.value).toBe("");
    expect(parentPrefill).toBe("");

    rerender(
      <ChatInput
        ref={inputRef}
        onSend={onSend}
        onCancel={onCancel}
        onNewChat={onNewChat}
        isStreaming={true}
        initialText={parentPrefill}
        onComposerCleared={() => {
          parentPrefill = "";
        }}
        agentId="agent-1"
        threadId="thread-1"
      />,
    );

    expect(textarea.value).toBe("");
  });
});
