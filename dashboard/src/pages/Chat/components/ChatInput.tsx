import {
  useState,
  useRef,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useTranslation } from "react-i18next";
import { message as antMessage } from "antd";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useSlashCommands } from "../../../hooks/useSlashCommands";
import SlashCommandMenu from "./SlashCommandMenu";
import { agentChatApi } from "../../../api/modules/agentChat";
import type { ChatAttachment } from "../hooks/useChat";
import type { ResolvedModel } from "../../../api/types";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import MentionPickerMenu from "./MentionPickerMenu";
import ChatInputPreviewBar from "./ChatInputPreviewBar";
import ChatInputActionsRow from "./ChatInputActionsRow";
import { useVoiceInput } from "../../../hooks/useVoiceInput";
import { useKeyboardOffset } from "../../../hooks/useKeyboardOffset";
import { useChatAttachments } from "../hooks/useChatAttachments";
import { useSlashMentionInput } from "../hooks/useSlashMentionInput";
import { stripThinkingTags } from "../utils/chatAttachments";
import { readInputDraft, writeInputDraft } from "../hooks/chatStore";
import styles from "../index.module.less";

/** Imperative handle exposed via ref for programmatic text injection. */
export interface ChatInputHandle {
  setPrefillText: (text: string) => void;
}

interface ChatInputProps {
  onSend: (text: string, attachments?: ChatAttachment[]) => void;
  onCancel: () => void;
  onNewChat: () => void;
  onUserInput?: () => void;
  browserRecording?: boolean;
  browserReplayBusy?: boolean;
  browserLastRecordingId?: string | null;
  onStartBrowserRecording?: () => void;
  onStopBrowserRecording?: () => void;
  onReplayBrowserRecording?: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  /** Pre-fill the input with this text on mount (e.g. navigated from another page). */
  initialText?: string;
  availableModels?: ResolvedModel[];
  selectedModel?: string | null;
  onModelChange?: (model: string | null) => void;
  availableConnectors?: {
    mcp_server_name: string;
    label: string;
    kind: string;
  }[];
  selectedConnectors?: string[];
  onConnectorsChange?: (names: string[]) => void;
  availableSkills?: SkillSpec[];
  selectedSkills?: string[];
  onSkillsChange?: (names: string[]) => void;
  availableAgents?: ChatAgentOption[];
  selectedTargetAgents?: string[];
  onTargetAgentsChange?: (ids: string[]) => void;
  agentId?: string | null;
  threadId?: string | null;
  defaultModel?: string | null;
  contextUsedTokens?: number | null;
  contextMaxTokens?: number;
}

const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput(
    {
      onSend,
      onCancel,
      onNewChat,
      onUserInput,
      browserRecording,
      browserReplayBusy,
      browserLastRecordingId,
      onStartBrowserRecording,
      onStopBrowserRecording,
      onReplayBrowserRecording,
      isStreaming,
      disabled,
      initialText = "",
      availableModels,
      selectedModel,
      onModelChange,
      availableConnectors,
      selectedConnectors = [],
      onConnectorsChange,
      availableSkills,
      selectedSkills = [],
      onSkillsChange,
      availableAgents = [],
      selectedTargetAgents = [],
      onTargetAgentsChange,
      agentId,
      threadId,
      defaultModel,
      contextUsedTokens = null,
      contextMaxTokens = 128_000,
    },
    ref,
  ) {
    const { t, i18n } = useTranslation();
    const { commands: slashCommands, labelFor } = useSlashCommands("ui");
    const isMobile = useIsMobile();
    useKeyboardOffset();
    const [text, setText] = useState(
      () => initialText || readInputDraft(agentId, threadId),
    );
    const [polishing, setPolishing] = useState(false);
    // Track whether the user has manually edited the text after a prefill.
    // Once they start editing, we must not overwrite their input with a new
    // initialText value (e.g. from a parent re-render or a stale effect).
    const userHasEditedRef = useRef(false);

    const handleVoiceText = useCallback(
      (spoken: string) => {
        setText((prev) => (prev.trim() ? `${prev.trim()} ${spoken}` : spoken));
        userHasEditedRef.current = true;
        onUserInput?.();
      },
      [onUserInput],
    );
    const {
      recording,
      transcribing,
      toggle: toggleVoice,
    } = useVoiceInput(handleVoiceText);

    // Expose an imperative handle so the parent can push a new prefill without
    // triggering a prop change that would cause a re-render cascade.
    useImperativeHandle(ref, () => ({
      setPrefillText: (newText: string) => {
        userHasEditedRef.current = false;
        prevInitialTextRef.current = newText;
        setText(newText);
        setTimeout(() => {
          const el = textareaRef.current;
          if (el) {
            el.focus();
            el.setSelectionRange(el.value.length, el.value.length);
          }
        }, 50);
      },
    }));
    // When the parent passes a non-empty initialText after mount (e.g. navigated
    // from cron-jobs), update the input value and move the cursor to the end.
    // Only fires when initialText actually changes AND the user hasn't started
    // editing yet (prevents overwriting mid-edit content).
    const prevInitialTextRef = useRef(initialText);
    const prevComposerKeyRef = useRef(`${agentId ?? ""}:${threadId ?? ""}`);
    useEffect(() => {
      if (
        initialText &&
        initialText !== prevInitialTextRef.current &&
        !userHasEditedRef.current
      ) {
        prevInitialTextRef.current = initialText;
        setText(initialText);
        // Focus the textarea so the user can immediately start editing
        setTimeout(() => {
          const el = textareaRef.current;
          if (el) {
            el.focus();
            el.setSelectionRange(el.value.length, el.value.length);
          }
        }, 50);
      }
    }, [initialText]);

    // Restore per-thread draft when switching conversations or remounting.
    useEffect(() => {
      const composerKey = `${agentId ?? ""}:${threadId ?? ""}`;
      if (composerKey === prevComposerKeyRef.current) return;
      prevComposerKeyRef.current = composerKey;
      userHasEditedRef.current = false;
      prevInitialTextRef.current = "";
      setText(initialText || readInputDraft(agentId, threadId));
    }, [agentId, threadId, initialText]);

    // Persist draft while typing so leaving /chat and returning keeps content.
    useEffect(() => {
      if (!agentId) return;
      const timer = window.setTimeout(() => {
        writeInputDraft(agentId, threadId, text);
      }, 250);
      return () => window.clearTimeout(timer);
    }, [text, agentId, threadId]);
    const {
      attachments,
      uploading,
      dragOver,
      fileInputRef,
      acceptAttr,
      handleFileSelect,
      handleFileChange,
      removeAttachment,
      clearAttachments,
      handlePaste,
      handleDragEnter,
      handleDragLeave,
      handleDragOver,
      handleDrop,
    } = useChatAttachments(agentId);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const submitRef = useRef<() => void>(() => {});

    const MIN_TEXTAREA_HEIGHT = isMobile ? 42 : 78;

    const {
      slashMenuOpen,
      slashMenuIndex,
      setSlashMenuIndex,
      mentionMenuOpen,
      mentionMenuIndex,
      setMentionMenuIndex,
      mentionQuery,
      mentionAgents,
      slashMenuFlat,
      slashMenuGroups,
      slashPickerGroups,
      slashMenuItems,
      mentionItems,
      runSlashCommand,
      matchSlashCommand,
      handleMentionSelect,
      handleSlashSelect,
      handleTextChange,
      handleKeyDown,
    } = useSlashMentionInput({
      text,
      setText,
      textareaRef,
      slashCommands,
      labelFor,
      locale: i18n.language,
      availableSkills,
      availableConnectors,
      availableAgents,
      agentId,
      selectedSkills,
      selectedConnectors,
      selectedTargetAgents,
      onSkillsChange,
      onConnectorsChange,
      onTargetAgentsChange,
      onSend,
      onNewChat,
      onCancel,
      isStreaming,
      onSubmitRef: submitRef,
      enterToSend: !isMobile,
    });

    const submitMessage = useCallback(() => {
      const trimmed = text.trim();
      if ((!trimmed && attachments.length === 0) || disabled) return;
      const slashItem = matchSlashCommand(trimmed);
      if (slashItem && slashItem.spec.client_action !== "none") {
        runSlashCommand(slashItem);
        return;
      }
      const ta = textareaRef.current;
      const prevHeight = ta ? ta.getBoundingClientRect().height : 0;
      onSend(trimmed, attachments.length > 0 ? attachments : undefined);
      setText("");
      writeInputDraft(agentId, threadId, "");
      clearAttachments();
      userHasEditedRef.current = false;
      prevInitialTextRef.current = "";
      requestAnimationFrame(() => {
        if (ta && prevHeight > MIN_TEXTAREA_HEIGHT) {
          ta.style.transition = "none";
          ta.style.height = `${prevHeight}px`;
          // eslint-disable-next-line @typescript-eslint/no-unused-expressions
          ta.offsetHeight;
          ta.style.transition = "";
          ta.style.height = `${MIN_TEXTAREA_HEIGHT}px`;
        }
      });
    }, [
      text,
      attachments,
      onSend,
      disabled,
      matchSlashCommand,
      runSlashCommand,
      clearAttachments,
      MIN_TEXTAREA_HEIGHT,
      agentId,
      threadId,
    ]);

    submitRef.current = submitMessage;

    // Pixel Avatar: listen for user input.
    useEffect(() => {
      if (onUserInput && text.length > 0) {
        onUserInput();
      }
    }, [text, onUserInput]);

    const adjustHeight = useCallback(
      (animate = false) => {
        const ta = textareaRef.current;
        if (!ta) return;
        // Disable transition during measurement to avoid visual glitches
        ta.style.transition = "none";
        ta.style.height = "auto";
        const target = Math.max(
          Math.min(ta.scrollHeight, 160),
          MIN_TEXTAREA_HEIGHT,
        );
        if (animate) {
          // Snap to current rendered height first (no transition), then animate to target
          const current = ta.getBoundingClientRect().height;
          ta.style.height = `${current}px`;
          // eslint-disable-next-line @typescript-eslint/no-unused-expressions
          ta.offsetHeight; // force reflow
          ta.style.transition = "";
          ta.style.height = `${target}px`;
        } else {
          ta.style.height = `${target}px`;
          // eslint-disable-next-line @typescript-eslint/no-unused-expressions
          ta.offsetHeight;
          ta.style.transition = "";
        }
      },
      [MIN_TEXTAREA_HEIGHT],
    );

    useEffect(() => {
      adjustHeight();
    }, [text, adjustHeight]);

    const handlePolish = useCallback(async () => {
      const draft = text.trim();
      if (!draft || !agentId || polishing || isStreaming || disabled) return;
      setPolishing(true);
      try {
        const result = await agentChatApi.polish(agentId, draft, selectedModel);
        const polished = stripThinkingTags(result.text?.trim() ?? "");
        if (!polished) {
          antMessage.error(t("chat.polish.emptyResult"));
          return;
        }
        userHasEditedRef.current = true;
        setText(polished);
        setTimeout(() => {
          const el = textareaRef.current;
          if (el) {
            el.focus();
            el.setSelectionRange(el.value.length, el.value.length);
          }
        }, 50);
      } catch (err: unknown) {
        antMessage.error(
          err instanceof Error ? err.message : t("chat.polish.failed"),
        );
      } finally {
        setPolishing(false);
      }
    }, [text, agentId, polishing, isStreaming, disabled, selectedModel, t]);

    const canSend = Boolean(
      (text.trim() || attachments.length > 0) && !disabled,
    );

    return (
      <div
        className={`${styles.chatInput} ${dragOver ? styles.dropActive : ""}`}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <div className={styles.inputWrapper}>
          <ChatInputPreviewBar
            attachments={attachments}
            uploading={uploading}
            selectedSkills={selectedSkills}
            selectedConnectors={selectedConnectors}
            selectedTargetAgents={selectedTargetAgents}
            selectedModel={selectedModel}
            availableSkills={availableSkills}
            availableConnectors={availableConnectors}
            availableAgents={availableAgents}
            onRemoveAttachment={removeAttachment}
            onSkillsChange={onSkillsChange}
            onConnectorsChange={onConnectorsChange}
            onTargetAgentsChange={onTargetAgentsChange}
            onModelChange={onModelChange}
          />

          <div className={styles.inputRow} style={{ position: "relative" }}>
            <textarea
              ref={textareaRef}
              className={styles.textarea}
              value={text}
              onChange={(e) => {
                userHasEditedRef.current = true;
                handleTextChange(e.target.value);
              }}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={t(
                "chatWelcome.inputPlaceholder",
                "Message Octop...",
              )}
              rows={1}
              disabled={disabled}
              enterKeyHint={isMobile ? "enter" : undefined}
            />
            {/*
            Slash badge (plan §14.5): octop's HarnessProcessor handles slash
            commands server-side. The composer doesn't intercept them — it
            just surfaces a small inline pill so the user sees they're
            issuing a command, not a regular message.
          */}
            {text.startsWith("/") && (
              <span
                data-testid="slash-badge"
                style={{
                  position: "absolute",
                  top: 6,
                  right: 8,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "2px 8px",
                  background: "var(--fn-color-brand-bg, rgba(79,110,247,0.12))",
                  color: "var(--fn-color-brand, #4f6ef7)",
                  border: "1px solid var(--fn-color-brand, #4f6ef7)",
                  borderRadius: 999,
                  fontSize: 11,
                  fontWeight: 600,
                  lineHeight: "16px",
                  pointerEvents: "none",
                  userSelect: "none",
                  letterSpacing: 0.2,
                }}
              >
                /<span style={{ fontWeight: 500 }}>slash</span>
              </span>
            )}
          </div>

          {mentionMenuOpen && mentionItems.length > 0 && (
            <MentionPickerMenu
              query={mentionQuery}
              skills={availableSkills ?? []}
              connectors={availableConnectors ?? []}
              agents={mentionAgents}
              activeIndex={mentionMenuIndex}
              onSelect={handleMentionSelect}
              onHover={setMentionMenuIndex}
            />
          )}

          {/* Slash command inline menu */}
          {slashMenuOpen && slashMenuFlat.length > 0 && (
            <div className={styles.slashMenu}>
              <SlashCommandMenu
                groups={slashMenuGroups}
                flatItems={slashMenuFlat}
                activeIndex={slashMenuIndex}
                disabled={isStreaming || disabled}
                variant="inline"
                itemsGridClassName={styles.slashMenuGrid}
                itemClassName={styles.slashMenuItem}
                activeClassName={styles.slashMenuItemActive}
                categoryClassName={styles.slashMenuCategory}
                labelClassName={styles.slashMenuLabel}
                cmdClassName={styles.slashMenuCmd}
                onSelect={handleSlashSelect}
                onHover={setSlashMenuIndex}
                footer={
                  <div className={styles.slashMenuHint}>
                    {t(
                      "slash.menuHint",
                      "↑↓ navigate · Enter confirm · Esc close",
                    )}
                  </div>
                }
              />
            </div>
          )}

          <ChatInputActionsRow
            isMobile={isMobile}
            isStreaming={isStreaming}
            disabled={disabled}
            canSend={canSend}
            text={text}
            polishing={polishing}
            uploading={uploading}
            recording={recording}
            transcribing={transcribing}
            browserRecording={browserRecording}
            browserReplayBusy={browserReplayBusy}
            browserLastRecordingId={browserLastRecordingId}
            onStartBrowserRecording={onStartBrowserRecording}
            onStopBrowserRecording={onStopBrowserRecording}
            onReplayBrowserRecording={onReplayBrowserRecording}
            agentId={agentId}
            threadId={threadId}
            contextUsedTokens={contextUsedTokens}
            contextMaxTokens={contextMaxTokens}
            availableModels={availableModels}
            selectedModel={selectedModel}
            onModelChange={onModelChange}
            defaultModel={defaultModel}
            availableConnectors={availableConnectors}
            selectedConnectors={selectedConnectors}
            onConnectorsChange={onConnectorsChange}
            availableSkills={availableSkills}
            selectedSkills={selectedSkills}
            onSkillsChange={onSkillsChange}
            availableExperts={availableAgents.filter(
              (a) => a.agent_id !== agentId,
            )}
            selectedTargetAgents={selectedTargetAgents}
            onTargetAgentsChange={onTargetAgentsChange}
            slashPickerGroups={slashPickerGroups}
            slashMenuItems={slashMenuItems}
            onSlashShortcutSelect={handleSlashSelect}
            onFileSelect={handleFileSelect}
            onNewChat={onNewChat}
            onPolish={() => void handlePolish()}
            onToggleVoice={() => toggleVoice()}
            onCancel={onCancel}
            onSubmit={submitMessage}
          />

          <input
            ref={fileInputRef}
            type="file"
            accept={acceptAttr}
            multiple
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
        </div>
        {!isMobile && (
          <p className={styles.aiDisclaimer}>{t("chatWelcome.aiDisclaimer")}</p>
        )}
      </div>
    );
  },
);

export default ChatInput;
