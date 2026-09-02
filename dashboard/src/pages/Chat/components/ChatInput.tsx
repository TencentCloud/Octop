import {
  useState,
  useRef,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useTranslation } from "react-i18next";
import { App } from "antd";

import { useIsMobile } from "../../../hooks/useIsMobile";
import { useSlashCommands } from "../../../hooks/useSlashCommands";
import SlashCommandMenu from "./SlashCommandMenu";
import { agentChatApi } from "../../../api/modules/agentChat";
import type { ChatAttachment } from "../hooks/useChat";
import type { ResolvedModel } from "../../../api/types";
import type { KnowledgeBase } from "../../../api/modules/knowledgeBases";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import MentionPickerMenu from "./MentionPickerMenu";
import ChatInputPreviewBar from "./ChatInputPreviewBar";
import ChatInputActionsRow from "./ChatInputActionsRow";
import ChatQueuedMessages from "./ChatQueuedMessages";
import { useVoiceInput } from "../../../hooks/useVoiceInput";
import { useKeyboardOffset } from "../../../hooks/useKeyboardOffset";
import { useChatAttachments } from "../hooks/useChatAttachments";
import { useSlashMentionInput } from "../hooks/useSlashMentionInput";
import { stripThinkingTags } from "../utils/chatAttachments";
import {
  consumePendingPrefillAttachments,
  readInputDraft,
  writeInputDraft,
} from "../hooks/chatStore";
import {
  buildComposerContext,
  resolveTurnModelRef,
} from "../utils/chatMessages";
import type {
  EnqueueChatItemInput,
  QueuedChatItem,
} from "../hooks/useChatMessageQueue";
import styles from "../index.module.less";

/** Imperative handle exposed via ref for programmatic text injection. */
export interface ChatInputHandle {
  setPrefillText: (text: string) => void;
  setPrefillComposer: (text: string, attachments?: ChatAttachment[]) => void;
}

interface ChatInputProps {
  onSend: (text: string, attachments?: ChatAttachment[]) => void;
  /** Queue a message while the current turn is still streaming. */
  onQueue?: (item: EnqueueChatItemInput) => "ok" | "empty" | "full";
  queuedItems?: QueuedChatItem[];
  onRemoveQueued?: (id: string) => void;
  onReclaimQueued?: (id: string) => QueuedChatItem | null;
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
  /** Called when the composer is cleared after a successful send/queue. */
  onComposerCleared?: () => void;
  availableModels?: ResolvedModel[];
  selectedModel?: string | null;
  onModelChange?: (model: string | null) => void;
  reasoningMode?: "auto" | "enabled" | "disabled";
  reasoningEffort?: string | null;
  onReasoningChange?: (
    mode: "auto" | "enabled" | "disabled",
    effort: string | null,
  ) => void;
  availableConnectors?: {
    mcp_server_name: string;
    label: string;
    kind: string;
  }[];
  selectedConnectors?: string[];
  onConnectorsChange?: (names: string[]) => void;
  availableKnowledgeBases?: KnowledgeBase[];
  selectedKnowledgeBaseIds?: string[];
  onKnowledgeBaseIdsChange?: (ids: string[]) => void;
  availableSkills?: SkillSpec[];
  selectedSkills?: string[];
  onSkillsChange?: (names: string[]) => void;
  availableAgents?: ChatAgentOption[];
  /**
   * Subset of experts the user can currently pick — only running ones
   * (stopped / failed experts would dispatch into an unloaded harness and
   * silently fail). Pass the same list as ``availableAgents`` if every
   * expert is guaranteed to be running.
   */
  availableExperts?: ChatAgentOption[];
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
      onQueue,
      queuedItems = [],
      onRemoveQueued,
      onReclaimQueued,
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
      onComposerCleared,
      availableModels,
      selectedModel,
      onModelChange,
      reasoningMode = "auto",
      reasoningEffort = null,
      onReasoningChange,
      availableConnectors,
      selectedConnectors = [],
      onConnectorsChange,
      availableKnowledgeBases,
      selectedKnowledgeBaseIds = [],
      onKnowledgeBaseIdsChange,
      availableSkills,
      selectedSkills = [],
      onSkillsChange,
      availableAgents = [],
      // Default ``availableExperts`` to the full projection so older callers
      // (and tests) keep working. Production callers in ``Chat/index.tsx``
      // explicitly pass the filtered list — keep that explicit to avoid
      // accidentally re-surfacing stopped experts in the @-picker.
      availableExperts = availableAgents,
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
    const { modal, message: antMessage } = App.useApp();
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
    // After submit, ignore one re-application of this exact initialText value
    // (parent may still hold the prefill string in a ref across the next render).
    const ignoreInitialTextRef = useRef<string | null>(null);

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
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const {
      attachments,
      uploading,
      dragOver,
      fileInputRef,
      handleFileSelect,
      handleFileChange,
      removeAttachment,
      clearAttachments,
      restoreAttachments,
      handlePaste,
      handleDragEnter,
      handleDragLeave,
      handleDragOver,
      handleDrop,
    } = useChatAttachments(agentId);

    // Expose an imperative handle so the parent can push a new prefill without
    // triggering a prop change that would cause a re-render cascade.
    useImperativeHandle(
      ref,
      () => ({
        setPrefillText: (newText: string) => {
          userHasEditedRef.current = false;
          ignoreInitialTextRef.current = null;
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
        setPrefillComposer: (
          newText: string,
          nextAttachments?: ChatAttachment[],
        ) => {
          userHasEditedRef.current = false;
          ignoreInitialTextRef.current = null;
          prevInitialTextRef.current = newText;
          setText(newText);
          if (nextAttachments && nextAttachments.length > 0) {
            restoreAttachments(
              nextAttachments.map((attachment) => ({ ...attachment })),
            );
          } else {
            clearAttachments();
          }
          setTimeout(() => {
            const el = textareaRef.current;
            if (el) {
              el.focus();
              el.setSelectionRange(el.value.length, el.value.length);
            }
          }, 50);
        },
      }),
      [clearAttachments, restoreAttachments],
    );

    // When the parent passes a non-empty initialText after mount (e.g. navigated
    // from cron-jobs), update the input value and move the cursor to the end.
    // Only fires when initialText actually changes AND the user hasn't started
    // editing yet (prevents overwriting mid-edit content).
    const prevInitialTextRef = useRef(initialText);
    const prevComposerKeyRef = useRef(`${agentId ?? ""}:${threadId ?? ""}`);
    useEffect(() => {
      if (
        ignoreInitialTextRef.current !== null &&
        initialText === ignoreInitialTextRef.current
      ) {
        // Stale post-submit prop — acknowledge without restoring cleared text.
        ignoreInitialTextRef.current = null;
        prevInitialTextRef.current = initialText;
        return;
      }
      if (ignoreInitialTextRef.current !== null) {
        // A different (or empty) prop arrived — stop ignoring.
        ignoreInitialTextRef.current = null;
      }
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
      ignoreInitialTextRef.current = null;
      prevInitialTextRef.current = "";
      setText(initialText || readInputDraft(agentId, threadId));
      const pendingAttachments = consumePendingPrefillAttachments();
      if (pendingAttachments.length > 0) {
        restoreAttachments(pendingAttachments);
      } else {
        clearAttachments();
      }
    }, [agentId, threadId, initialText, clearAttachments, restoreAttachments]);

    // Persist draft while typing so leaving /chat and returning keeps content.
    useEffect(() => {
      if (!agentId) return;
      const timer = window.setTimeout(() => {
        writeInputDraft(agentId, threadId, text);
      }, 250);
      return () => window.clearTimeout(timer);
    }, [text, agentId, threadId]);
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
      availableExperts,
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

    const resetComposerAfterSubmit = useCallback(
      (prevHeight: number, submittedText: string) => {
        setText("");
        writeInputDraft(agentId, threadId, "");
        clearAttachments();
        userHasEditedRef.current = false;
        // Parent may re-pass the same prefill as initialText on the next render
        // (skill-card / cron keep it in a ref). Ignore that exact value once.
        ignoreInitialTextRef.current = submittedText;
        prevInitialTextRef.current = initialText;
        onComposerCleared?.();
        requestAnimationFrame(() => {
          const ta = textareaRef.current;
          if (ta && prevHeight > MIN_TEXTAREA_HEIGHT) {
            ta.style.transition = "none";
            ta.style.height = `${prevHeight}px`;
            // eslint-disable-next-line @typescript-eslint/no-unused-expressions
            ta.offsetHeight;
            ta.style.transition = "";
            ta.style.height = `${MIN_TEXTAREA_HEIGHT}px`;
          }
        });
      },
      [
        agentId,
        threadId,
        clearAttachments,
        MIN_TEXTAREA_HEIGHT,
        initialText,
        onComposerCleared,
      ],
    );

    const submitMessage = useCallback(() => {
      const trimmed = text.trim();
      if ((!trimmed && attachments.length === 0) || disabled) return;
      const slashItem = matchSlashCommand(trimmed);
      if (slashItem && slashItem.spec.client_action !== "none") {
        // Slash actions are never queued — run immediately or leave input alone.
        if (isStreaming) return;
        runSlashCommand(slashItem);
        return;
      }
      const ta = textareaRef.current;
      const prevHeight = ta ? ta.getBoundingClientRect().height : 0;

      if (isStreaming) {
        if (!onQueue) return;
        const result = onQueue({
          text: trimmed,
          attachments: attachments.length > 0 ? attachments : undefined,
          composerContext: buildComposerContext({
            skills: selectedSkills,
            connectors: selectedConnectors,
            knowledgeBaseIds: selectedKnowledgeBaseIds,
            targetAgents: selectedTargetAgents,
            selectedModel,
            reasoningMode,
            reasoningEffort,
          }),
          modelRef: resolveTurnModelRef(selectedModel, defaultModel),
        });
        if (result === "full") {
          antMessage.warning(t("chat.queue.full"));
          return;
        }
        if (result === "empty") return;
        resetComposerAfterSubmit(prevHeight, trimmed);
        return;
      }

      onSend(trimmed, attachments.length > 0 ? attachments : undefined);
      resetComposerAfterSubmit(prevHeight, trimmed);
    }, [
      text,
      attachments,
      onSend,
      onQueue,
      disabled,
      isStreaming,
      matchSlashCommand,
      runSlashCommand,
      resetComposerAfterSubmit,
      selectedSkills,
      selectedConnectors,
      selectedTargetAgents,
      selectedModel,
      reasoningMode,
      reasoningEffort,
      defaultModel,
      t,
    ]);

    submitRef.current = submitMessage;

    const handleReclaimQueued = useCallback(
      (id: string) => {
        if (!onReclaimQueued) return;
        const apply = () => {
          const item = onReclaimQueued(id);
          if (!item) return;
          userHasEditedRef.current = true;
          setText(item.text);
          restoreAttachments(item.attachments ?? []);
          const ctx = item.composerContext;
          if (ctx) {
            onSkillsChange?.(ctx.skills ?? []);
            onConnectorsChange?.(ctx.connectors ?? []);
            onKnowledgeBaseIdsChange?.(ctx.knowledgeBaseIds ?? []);
            onTargetAgentsChange?.(ctx.targetAgents ?? []);
            if (ctx.model !== undefined) {
              onModelChange?.(ctx.model);
            } else if (item.modelRef !== undefined) {
              onModelChange?.(item.modelRef);
            }
            if (ctx.reasoningMode !== undefined) {
              onReasoningChange?.(
                ctx.reasoningMode,
                ctx.reasoningEffort || null,
              );
            }
          } else if (item.modelRef !== undefined) {
            onModelChange?.(item.modelRef);
          }
          setTimeout(() => {
            const el = textareaRef.current;
            if (el) {
              el.focus();
              el.setSelectionRange(el.value.length, el.value.length);
            }
          }, 50);
        };

        if (text.trim() || attachments.length > 0) {
          modal.confirm({
            title: t("chat.queue.reclaimOverwriteTitle"),
            content: t("chat.queue.reclaimOverwrite"),
            okText: t("common.confirm", "确认"),
            cancelText: t("common.cancel", "取消"),
            onOk: apply,
          });
          return;
        }
        apply();
      },
      [
        onReclaimQueued,
        restoreAttachments,
        text,
        attachments.length,
        t,
        onSkillsChange,
        onConnectorsChange,
        onKnowledgeBaseIdsChange,
        onTargetAgentsChange,
        onModelChange,
        onReasoningChange,
      ],
    );

    // Pixel Avatar: listen for user input.
    useEffect(() => {
      if (onUserInput && text.length > 0) {
        onUserInput();
      }
    }, [text, onUserInput]);

    const adjustHeight = useCallback(() => {
      const ta = textareaRef.current;
      if (!ta) return;
      // Measure the content height on a detached clone instead of collapsing
      // the live textarea to height:"auto". That transient shrink reflows the
      // flex layout and makes the message list viewport (a sibling above the
      // composer) grow for a moment; browsers clamp the list scrollTop to the
      // larger viewport and the clamp STICKS after the height is restored —
      // while a reply streams, follow-pins then snap the list back down, i.e.
      // the per-keystroke up/down jitter. A clone never touches live layout.
      const target = (() => {
        const clone = ta.cloneNode(false) as HTMLTextAreaElement;
        clone.value = ta.value;
        const rect = ta.getBoundingClientRect();
        clone.style.cssText = [
          "position:fixed",
          "left:-9999px",
          "top:0",
          "visibility:hidden",
          "height:auto",
          "min-height:0",
          "max-height:none",
          "transition:none",
          `width:${rect.width}px`,
        ].join(";");
        document.body.appendChild(clone);
        const h = clone.scrollHeight;
        document.body.removeChild(clone);
        return Math.max(Math.min(h, 160), MIN_TEXTAREA_HEIGHT);
      })();
      const current = ta.getBoundingClientRect().height;
      if (Math.abs(target - current) < 0.5) return; // height unchanged
      // Disable transition during the write so the resize is instant.
      ta.style.transition = "none";
      ta.style.height = `${target}px`;
      // eslint-disable-next-line @typescript-eslint/no-unused-expressions
      ta.offsetHeight; // force reflow
      ta.style.transition = "";
    }, [MIN_TEXTAREA_HEIGHT]);

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
        {onRemoveQueued && onReclaimQueued && (
          <ChatQueuedMessages
            items={queuedItems}
            onRemove={onRemoveQueued}
            onReclaim={handleReclaimQueued}
          />
        )}
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
            availableKnowledgeBases={availableKnowledgeBases}
            availableAgents={availableAgents}
            onRemoveAttachment={removeAttachment}
            onSkillsChange={onSkillsChange}
            onConnectorsChange={onConnectorsChange}
            selectedKnowledgeBaseIds={selectedKnowledgeBaseIds}
            onKnowledgeBaseIdsChange={onKnowledgeBaseIdsChange}
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
                  background: "var(--fn-color-brand-bg)",
                  color: "var(--fn-color-brand)",
                  border: "1px solid var(--fn-color-brand)",
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
            reasoningMode={reasoningMode}
            reasoningEffort={reasoningEffort}
            onReasoningChange={onReasoningChange}
            defaultModel={defaultModel}
            availableConnectors={availableConnectors}
            selectedConnectors={selectedConnectors}
            onConnectorsChange={onConnectorsChange}
            availableKnowledgeBases={availableKnowledgeBases}
            selectedKnowledgeBaseIds={selectedKnowledgeBaseIds}
            onKnowledgeBaseIdsChange={onKnowledgeBaseIdsChange}
            availableSkills={availableSkills}
            selectedSkills={selectedSkills}
            onSkillsChange={onSkillsChange}
            availableExperts={availableExperts.filter(
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
