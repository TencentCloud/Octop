import { memo, useMemo, useState, useCallback, useRef, useEffect } from "react";
import { Image, Button, Tooltip } from "antd";
import { message as antMessage } from "@/utils/antdMessage";

import Markdown from "../../../components/Markdown/LazyMarkdown";
import {
  Copy,
  Check,
  RotateCcw,
  Pencil,
  Volume2,
  Settings,
  GitFork,
  PanelRight,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { ChatAttachment, ChatMessage } from "../hooks/useChat";
import type { ComposerTagLookups } from "./UserMessageComposerTags";
import UserMessageComposerTags from "./UserMessageComposerTags";
import { deriveMessageContent } from "../utils/messageContent";
import { inferKindFromNameAndMime } from "../utils/chatAttachments";
import { ChatMediaPlayer } from "./ChatMediaPlayer";
import { useAuthImageSrc } from "../../../hooks/useAuthImageSrc";
import {
  agentAttachmentAccessUrl,
  isDataUrl,
  workspacePathFromAccessUrl,
} from "../../../utils/toolMediaBlocks";
import { formatMessageTime } from "../../../utils/formatMessageTime";
import { copyText } from "../../../utils/copyText";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { useVoiceOutputContext } from "../../../context/VoiceOutputContext";
import { prepareSpeechText } from "../../../utils/plainTextForSpeech";
import {
  chatStreamErrorAction,
  formatChatStreamError,
  isChatStreamError,
} from "../../../utils/chatStreamError";
import { MessageFileCard } from "./MessageFileCard";
import styles from "../index.module.less";
import {
  DefaultToolRenderer,
  builtinPluginHost,
  createPluginUiHost,
  parseOctopToolOutput,
  resolveToolRenderer,
  useToolRendererVersion,
  type ToolRenderProps,
  type ToolRenderStatus,
} from "../../../plugins/toolRenderers";
import { BuiltinOctopUiFallback } from "../../../plugins/toolRenderers/builtin/BuiltinOctopUiFallback";
import { ToolUiErrorBoundary } from "../../../plugins/toolRenderers/ToolUiErrorBoundary";
import { lookupPluginIdForTool } from "../../../plugins/toolRenderers/toolPluginIndex";
import { useChatToolDock } from "../ChatToolDockContext";
import { useToolUiDockButtonStyle } from "../hooks/useToolUiDockButtonStyle";
import type { ParsedToolOutput } from "../../../plugins/toolRenderers/types";
import type { ToolRendererRegistration } from "../../../plugins/toolRenderers/types";

interface MessageBubbleProps {
  message: ChatMessage;
  agentId?: string | null;
  composerLookups?: ComposerTagLookups;
  onRegenerate?: (messageId: string) => void;
  onEditUserMessage?: (messageId: string, newText: string) => void;
  onForkAssistantMessage?: (messageId: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
  onHitlDecision?: (
    decisions: Array<{ type: string; message?: string }>,
  ) => void;

  /** When true, the outer bubble uses reduced spacing (part of a group). */
  compact?: boolean;
  /** Position within an assistant group — controls border-radius & meta visibility. */
  groupPosition?: "first" | "middle" | "last" | "only";
  onRunShellCommand?: (code: string) => void;
  shellCommandDisabled?: boolean;
  shellCommandDisabledTitle?: string;
}

function formatTokenUsage(
  usage: ChatMessage["usage"],
  labels: { input: string; output: string; total: string; cacheHit: string },
): string[] {
  if (!usage) return [];

  const parts: string[] = [];
  if (typeof usage.input_tokens === "number") {
    parts.push(`${usage.input_tokens} ${labels.input}`);
  }
  if (
    typeof usage.cache_read_tokens === "number" &&
    usage.cache_read_tokens > 0
  ) {
    const percent =
      typeof usage.input_tokens === "number" && usage.input_tokens > 0
        ? ` (${Math.round(
            (usage.cache_read_tokens / usage.input_tokens) * 100,
          )}%)`
        : "";
    parts.push(`${usage.cache_read_tokens} ${labels.cacheHit}${percent}`);
  }
  if (typeof usage.output_tokens === "number") {
    parts.push(`${usage.output_tokens} ${labels.output}`);
  }
  if (typeof usage.total_tokens === "number") {
    parts.push(`${usage.total_tokens} ${labels.total}`);
  }
  return parts;
}

function formatErrorDebugTags(errorInfo: ChatMessage["errorInfo"]): string[] {
  if (!errorInfo) return [];

  const parts: string[] = [];
  if (errorInfo.code) {
    parts.push(`code: ${errorInfo.code}`);
  }
  if (errorInfo.source) {
    parts.push(`source: ${errorInfo.source}`);
  }
  if (typeof errorInfo.status_code === "number") {
    parts.push(`HTTP ${errorInfo.status_code}`);
  }
  if (errorInfo.retryable) {
    parts.push("retryable");
  }
  return parts;
}

/**
 * A single image that:
 * - For authenticated API URLs: fetches with auth header and converts to blob URL.
 * - For data URLs: converts to blob URL so preview/download works reliably.
 * - For signed agent file URLs: auto-refreshes on load failure.
 */
function RefreshableImage({
  url,
  filename,
  workspacePath,
  mediaType,
  idx,
  agentId,
}: {
  url: string;
  filename?: string;
  workspacePath?: string;
  mediaType?: string;
  idx: number;
  agentId?: string | null;
}) {
  const { t } = useTranslation();
  const resolvedUrl = useMemo(() => {
    if (url && !url.startsWith("workspace://")) return url;
    const path =
      workspacePath ||
      (url.startsWith("workspace://")
        ? url.slice("workspace://".length).replace(/^\/+/, "")
        : "") ||
      workspacePathFromAccessUrl(url);
    if (path && agentId) {
      return agentAttachmentAccessUrl(agentId, path, mediaType);
    }
    return url;
  }, [url, workspacePath, agentId, mediaType]);
  const { src, loadState, setSrc } = useAuthImageSrc(resolvedUrl, filename);
  const retried = useRef(false);

  const handleError = useCallback(() => {
    if (retried.current) return;
    retried.current = true;

    if (isDataUrl(resolvedUrl)) return;

    const path = workspacePath || workspacePathFromAccessUrl(resolvedUrl);
    if (!path || !agentId) return;

    setSrc(agentAttachmentAccessUrl(agentId, path, mediaType));
  }, [resolvedUrl, agentId, workspacePath, mediaType, setSrc]);

  if (loadState === "loading") {
    return (
      <div
        aria-hidden
        style={{
          width: 300,
          height: 300,
          backgroundColor: "#f0f0f0",
          borderRadius: 8,
        }}
      />
    );
  }

  if (loadState === "error" || !src) {
    return (
      <div
        style={{
          width: 300,
          height: 300,
          backgroundColor: "#fff1f0",
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#cf1322",
          fontSize: 12,
        }}
      >
        {t("chat.imageLoadFailed")}
      </div>
    );
  }

  return (
    <Image
      key={`${src}-${idx}`}
      src={src}
      alt={filename || `image-${idx}`}
      className={styles.messageImage}
      width="auto"
      style={{
        maxWidth: 300,
        maxHeight: 300,
        borderRadius: 8,
        objectFit: "contain",
      }}
      onError={handleError}
    />
  );
}

function ImageGallery({
  images,
  agentId,
}: {
  images: Array<{
    url: string;
    filename?: string;
    workspacePath?: string;
    mediaType?: string;
  }>;
  agentId?: string | null;
}) {
  if (!images || images.length === 0) return null;

  return (
    <div className={styles.messageImages}>
      <Image.PreviewGroup>
        {images.map((img, idx) => (
          <RefreshableImage
            key={`${img.url}-${idx}`}
            url={img.url}
            filename={img.filename}
            workspacePath={img.workspacePath}
            mediaType={img.mediaType}
            idx={idx}
            agentId={agentId}
          />
        ))}
      </Image.PreviewGroup>
    </div>
  );
}

function FileAttachmentList({
  files,
  agentId,
}: {
  files: ChatAttachment[];
  agentId?: string | null;
}) {
  if (!files || files.length === 0) return null;

  return (
    <div className={styles.messageFiles}>
      {files.map((file, idx) => (
        <MessageFileCard
          key={`${file.url}-${idx}`}
          url={file.url}
          filename={file.filename}
          agentId={agentId}
          workspacePath={file.workspacePath}
        />
      ))}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (!text) return;
    const ok = await copyText(text);
    if (!ok) {
      antMessage.error(t("common.copyFailed"));
      return;
    }
    setCopied(true);
    antMessage.success(t("common.copied"));
    setTimeout(() => setCopied(false), 2000);
  }, [text, t]);

  return (
    <button
      className={styles.msgCopyBtn}
      onClick={handleCopy}
      title={t("common.copy", "复制")}
      type="button"
      aria-label={t("common.copy", "复制")}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

function canDockToolUi(
  registration: ToolRendererRegistration | null,
  parsed: ParsedToolOutput,
): boolean {
  if (parsed.octopUi) return true;
  return (
    registration != null &&
    registration.id !== "default" &&
    registration.pluginId !== "builtin"
  );
}

function toolUiDockLabel(
  toolData: NonNullable<ChatMessage["toolData"]>,
): string {
  return toolData.displayName?.trim() || toolData.name?.trim() || "Tool";
}

export function ToolDetailsInline({
  toolData,
  isStreaming,
  onAcpPermissionSelect,
  hideMediaPreview = false,
  agentId = null,
  forceInline = false,
}: {
  toolData: NonNullable<ChatMessage["toolData"]>;
  isStreaming: boolean;
  onAcpPermissionSelect?: (message: string) => void;
  hideMediaPreview?: boolean;
  agentId?: string | null;
  /** When true, skip dock attach / placeholder (full renderer in side panel). */
  forceInline?: boolean;
}) {
  const { t } = useTranslation();
  const toolDock = useChatToolDock();
  // Plugin UIs load async after mount — bump forces resolve() to re-run.
  const rendererVersion = useToolRendererVersion();
  const parsed = useMemo(
    () => parseOctopToolOutput(toolData.output),
    [toolData.output],
  );
  const pluginId =
    toolData.pluginId ?? lookupPluginIdForTool(toolData.name) ?? "builtin";

  const registration = useMemo(
    () =>
      resolveToolRenderer({
        toolName: toolData.name,
        pluginId: pluginId === "builtin" ? null : pluginId,
        parsed,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rendererVersion invalidates registry lookups
    [toolData.name, pluginId, parsed, rendererVersion],
  );

  const status: ToolRenderStatus = toolData.errorCode
    ? "error"
    : toolData.output !== undefined
    ? "done"
    : "running";

  let args: unknown = toolData.arguments;
  if (typeof toolData.arguments === "string") {
    try {
      args = JSON.parse(toolData.arguments);
    } catch {
      args = toolData.arguments;
    }
  }

  const props: ToolRenderProps = {
    pluginId: registration?.pluginId ?? pluginId,
    toolName: toolData.name ?? "",
    displayName: toolData.displayName,
    callId: toolData.callId,
    status,
    args,
    data:
      parsed.data !== undefined
        ? parsed.data
        : parsed.isJson
        ? parsed.raw
        : toolData.output,
    textFallback: parsed.text,
    host:
      registration && registration.pluginId !== "builtin"
        ? createPluginUiHost(registration.pluginId)
        : builtinPluginHost,
    output: toolData.output,
    isStreaming,
    hideMediaPreview,
    onAcpPermissionSelect,
    agentId,
  };

  const dockable = canDockToolUi(registration ?? null, parsed);
  const callId = toolData.callId;
  const isDocked =
    !forceInline &&
    dockable &&
    !!callId &&
    (toolDock?.isToolUiDocked(callId) ?? false);

  const showDockButton =
    !forceInline && !isDocked && dockable && !!callId && !!toolDock;
  const { wrapRef, buttonStyle } = useToolUiDockButtonStyle(showDockButton, [
    toolData.output,
    registration?.id,
    rendererVersion,
  ]);

  const openInDock = useCallback(() => {
    if (!callId || !toolDock) return;
    toolDock.openToolUiPanel({
      callId,
      title: toolUiDockLabel(toolData),
      toolName: toolData.name,
    });
  }, [callId, toolData, toolDock]);

  const dockActions = showDockButton ? (
    <div className={styles.toolUiDockActions} style={buttonStyle}>
      <Tooltip title={t("chat.openToolUiInDock", "Open in side panel")}>
        <button
          type="button"
          className={styles.toolUiDockBtn}
          onClick={openInDock}
          aria-label={t("chat.openToolUiInDock", "Open in side panel")}
        >
          <PanelRight size={14} strokeWidth={2} aria-hidden />
        </button>
      </Tooltip>
    </div>
  ) : null;

  if (isDocked) {
    return (
      <button
        type="button"
        className={styles.toolUiDockPlaceholder}
        onClick={() => toolDock?.focusToolUiPanel(callId!)}
        title={t("chat.toolUiDockedOpen", "Open side panel")}
      >
        <PanelRight size={16} strokeWidth={2} aria-hidden />
        <span className={styles.toolUiDockPlaceholderTitle}>
          {toolUiDockLabel(toolData)}
        </span>
        <span className={styles.toolUiDockPlaceholderHint}>
          {t("chat.toolUiDockedHint", "Moved to side panel")}
        </span>
      </button>
    );
  }

  if (registration && registration.id !== "default") {
    const Comp = registration.component;
    return (
      <div
        ref={wrapRef}
        data-octop-tool-renderer=""
        className={styles.toolUiRendererWrap}
      >
        <ToolUiErrorBoundary propsForFallback={props}>
          <Comp {...props} />
        </ToolUiErrorBoundary>
        {dockActions}
      </div>
    );
  }

  // Structured plugin envelope without a loaded custom renderer — still show a card.
  if (parsed.octopUi) {
    return (
      <div
        ref={wrapRef}
        data-octop-tool-renderer=""
        className={styles.toolUiRendererWrap}
      >
        <BuiltinOctopUiFallback {...props} />
        {dockActions}
      </div>
    );
  }

  return (
    <div data-octop-tool-renderer="">
      <DefaultToolRenderer {...props} />
    </div>
  );
}

function MessageBubble({
  message,
  agentId = null,
  composerLookups,
  onRegenerate,
  onEditUserMessage,
  onForkAssistantMessage,
  forkDisabled,
  forkDisabledHint,
  onHitlDecision,
  compact,
  groupPosition = "only",
  onRunShellCommand,
  shellCommandDisabled,
  shellCommandDisabledTitle,
}: MessageBubbleProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const serverTimezone = useServerTimezone();

  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(message.content);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);

  const { speakingId, speak } = useVoiceOutputContext();

  const handleEditSubmit = useCallback(() => {
    if (onEditUserMessage && editText.trim()) {
      onEditUserMessage(message.id, editText.trim());
    }
    setIsEditing(false);
  }, [onEditUserMessage, message.id, editText]);

  const handleEditCancel = useCallback(() => {
    setEditText(message.content);
    setIsEditing(false);
  }, [message.content]);

  // Grow the edit box with content so short/long messages both feel usable.
  useEffect(() => {
    if (!isEditing) return;
    const el = editTextareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 120), 360)}px`;
  }, [isEditing, editText]);
  const usageParts = useMemo(
    () =>
      formatTokenUsage(message.usage, {
        input: t("chatUsage.input"),
        output: t("chatUsage.output"),
        total: t("chatUsage.total"),
        cacheHit: t("chatUsage.cacheHit"),
      }),
    [message.usage, t],
  );
  const errorDebugTags = useMemo(
    () => formatErrorDebugTags(message.errorInfo),
    [message.errorInfo],
  );

  const { textContent } = useMemo(
    () => deriveMessageContent(message),
    [message],
  );
  const speechText = useMemo(
    () => prepareSpeechText(textContent),
    [textContent],
  );

  if (message.hitlData) {
    const actions = message.hitlData.action_requests ?? [];
    const hitlStatus = message.hitlData.status ?? "pending";
    return (
      <div
        className={`${styles.bubble} ${styles.assistantBubble} ${
          compact ? styles.compact : ""
        }`}
      >
        <div className={styles.hitlCard}>
          <div className={styles.hitlTitle}>
            {t("chat.hitl.title", "Tool approval required")}
          </div>
          {actions.map((action, idx) => (
            <div key={`${action.name}-${idx}`} className={styles.hitlAction}>
              <code>{action.name}</code>
              {action.args && Object.keys(action.args).length > 0 && (
                <pre className={styles.inlineToolCode}>
                  {JSON.stringify(action.args, null, 2)}
                </pre>
              )}
            </div>
          ))}
          {hitlStatus === "pending" && onHitlDecision ? (
            <div className={styles.acpPermissionActions}>
              <Button
                type="primary"
                onClick={() =>
                  onHitlDecision(actions.map(() => ({ type: "approve" })))
                }
              >
                {t("chat.hitl.approve", "Approve")}
              </Button>
              <Button
                danger
                onClick={() =>
                  onHitlDecision(
                    actions.map(() => ({
                      type: "reject",
                      message: t("chat.hitl.rejected", "Rejected by user"),
                    })),
                  )
                }
              >
                {t("chat.hitl.reject", "Reject")}
              </Button>
            </div>
          ) : hitlStatus !== "pending" ? (
            <div
              className={`${styles.hitlResolved} ${
                hitlStatus === "approved"
                  ? styles.hitlResolvedApproved
                  : styles.hitlResolvedRejected
              }`}
            >
              {hitlStatus === "approved"
                ? t("chat.hitl.approved", "Approved")
                : t("chat.hitl.rejectedLabel", "Rejected")}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const hasToolData = !!message.toolData;
  const looksLikeStreamError =
    !isUser && !hasToolData && !isStreaming && isChatStreamError(textContent);
  const isError = message.status === "error" || looksLikeStreamError;
  const errorBodyText = isError
    ? formatChatStreamError(textContent, t)
    : textContent;
  const errorAction = isError ? chatStreamErrorAction(textContent) : null;
  const attachments = message.attachments || [];
  const imageAttachments = attachments.filter(
    (attachment) =>
      inferKindFromNameAndMime(
        attachment.mediaType,
        attachment.filename,
        attachment.kind,
      ) === "image",
  );
  const videoAttachments = attachments.filter(
    (attachment) =>
      inferKindFromNameAndMime(
        attachment.mediaType,
        attachment.filename,
        attachment.kind,
      ) === "video",
  );
  const audioAttachments = attachments.filter(
    (attachment) =>
      inferKindFromNameAndMime(
        attachment.mediaType,
        attachment.filename,
        attachment.kind,
      ) === "audio",
  );
  const fileAttachments = attachments.filter(
    (attachment) =>
      inferKindFromNameAndMime(
        attachment.mediaType,
        attachment.filename,
        attachment.kind,
      ) === "file",
  );
  const hasAttachments = attachments.length > 0;

  // Determine if this bubble is at the top/bottom of an assistant group
  const isLastInGroup = groupPosition === "last" || groupPosition === "only";

  // For skip-render checks: answer bubble only shows text and attachments.
  if (!isUser && !textContent && !hasAttachments) {
    return null;
  }

  if (!isUser && !hasAttachments && textContent && !textContent.trim()) {
    return null;
  }

  // Build group position CSS class for assistant bubble styling
  const groupCls =
    !isUser && !isError
      ? groupPosition === "first"
        ? styles.groupFirst
        : groupPosition === "middle"
        ? styles.groupMiddle
        : groupPosition === "last"
        ? styles.groupLast
        : ""
      : "";

  return (
    <div
      className={`${styles.messageBubble} ${
        isUser ? styles.userBubble : styles.assistantBubble
      } ${isError ? styles.errorBubble : ""} ${
        compact ? styles.compactBubble : ""
      }`}
    >
      <div className={styles.bubbleContent}>
        {isUser ? (
          <div className={styles.userMsgRow}>
            {isEditing ? (
              <div className={styles.editArea}>
                <textarea
                  ref={editTextareaRef}
                  className={styles.editTextarea}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  autoFocus
                  rows={4}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleEditSubmit();
                    }
                    if (e.key === "Escape") handleEditCancel();
                  }}
                />
                <div className={styles.editActions}>
                  <button
                    className={styles.editSaveBtn}
                    onClick={handleEditSubmit}
                    type="button"
                  >
                    {t("common.save", "保存并重新发送")}
                  </button>
                  <button
                    className={styles.editCancelBtn}
                    onClick={handleEditCancel}
                    type="button"
                  >
                    {t("common.cancel", "取消")}
                  </button>
                </div>
              </div>
            ) : (
              <div className={styles.userMsgColumn}>
                <UserMessageComposerTags
                  context={message.composerContext}
                  lookups={composerLookups}
                />
                <div className={styles.userText}>
                  {imageAttachments.length > 0 && (
                    <ImageGallery images={imageAttachments} agentId={agentId} />
                  )}
                  {videoAttachments.length > 0 && (
                    <div className={styles.messageMediaList}>
                      {videoAttachments.map((attachment, idx) => (
                        <ChatMediaPlayer
                          key={`${attachment.url}-${idx}`}
                          url={attachment.url}
                          filename={attachment.filename}
                          workspacePath={attachment.workspacePath}
                          mediaType={attachment.mediaType}
                          kind="video"
                          agentId={agentId}
                        />
                      ))}
                    </div>
                  )}
                  {audioAttachments.length > 0 && (
                    <div className={styles.messageMediaList}>
                      {audioAttachments.map((attachment, idx) => (
                        <ChatMediaPlayer
                          key={`${attachment.url}-${idx}`}
                          url={attachment.url}
                          filename={attachment.filename}
                          workspacePath={attachment.workspacePath}
                          mediaType={attachment.mediaType}
                          kind="audio"
                          agentId={agentId}
                        />
                      ))}
                    </div>
                  )}
                  {fileAttachments.length > 0 && (
                    <FileAttachmentList
                      files={fileAttachments}
                      agentId={agentId}
                    />
                  )}
                  {message.content && <div>{message.content}</div>}
                </div>
                {(message.content || onEditUserMessage) && (
                  <div className={styles.userMsgActions} role="group">
                    {message.content ? (
                      <CopyButton text={message.content} />
                    ) : null}
                    {onEditUserMessage ? (
                      <button
                        className={styles.msgActionBtn}
                        onClick={() => {
                          setEditText(message.content);
                          setIsEditing(true);
                        }}
                        title={t("common.edit")}
                        type="button"
                        aria-label={t("common.edit")}
                      >
                        <Pencil size={14} />
                      </button>
                    ) : null}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <>
            {isError ? (
              <div className={styles.errorMessageBox}>
                <div className={styles.errorMessageHeader}>
                  <span className={styles.errorMessageIcon}>⚠</span>
                  <span className={styles.errorMessageTitle}>
                    {t("chat.errorOccurred", "出现错误")}
                  </span>
                </div>
                {errorBodyText && (
                  <div className={styles.errorMessageBody}>{errorBodyText}</div>
                )}
                {errorDebugTags.length > 0 && (
                  <div className={styles.errorDebugRow}>
                    {errorDebugTags.map((tag) => (
                      <span key={tag} className={styles.errorDebugTag}>
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                {(errorAction || onRegenerate) && (
                  <div className={styles.errorActionRow}>
                    {errorAction && (
                      <button
                        className={styles.errorConfigBtn}
                        onClick={() => navigate(errorAction.path)}
                        type="button"
                      >
                        <Settings size={13} />
                        {t(errorAction.labelKey)}
                      </button>
                    )}
                    {onRegenerate && (
                      <button
                        className={styles.errorRetryBtn}
                        onClick={() => onRegenerate(message.id)}
                        type="button"
                      >
                        <RotateCcw size={13} />
                        {t("chat.retry", "重试")}
                      </button>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className={`${styles.assistantText} ${groupCls}`}>
                {imageAttachments.length > 0 && (
                  <ImageGallery images={imageAttachments} agentId={agentId} />
                )}
                {videoAttachments.length > 0 && (
                  <div className={styles.messageMediaList}>
                    {videoAttachments.map((attachment, idx) => (
                      <ChatMediaPlayer
                        key={`${attachment.url}-${idx}`}
                        url={attachment.url}
                        filename={attachment.filename}
                        workspacePath={attachment.workspacePath}
                        mediaType={attachment.mediaType}
                        kind="video"
                        agentId={agentId}
                      />
                    ))}
                  </div>
                )}
                {audioAttachments.length > 0 && (
                  <div className={styles.messageMediaList}>
                    {audioAttachments.map((attachment, idx) => (
                      <ChatMediaPlayer
                        key={`${attachment.url}-${idx}`}
                        url={attachment.url}
                        filename={attachment.filename}
                        workspacePath={attachment.workspacePath}
                        mediaType={attachment.mediaType}
                        kind="audio"
                        agentId={agentId}
                      />
                    ))}
                  </div>
                )}
                {fileAttachments.length > 0 && (
                  <FileAttachmentList
                    files={fileAttachments}
                    agentId={agentId}
                  />
                )}
                {textContent && (
                  <Markdown
                    content={textContent}
                    isStreaming={isStreaming}
                    onRunShellCommand={onRunShellCommand}
                    shellCommandDisabled={shellCommandDisabled}
                    shellCommandDisabledTitle={shellCommandDisabledTitle}
                  />
                )}
              </div>
            )}
          </>
        )}
        {/* Meta row: only show on the last message in a group (or standalone messages) */}
        {isLastInGroup &&
          !hasToolData &&
          (message.timestamp > 0 || usageParts.length > 0) && (
            <div
              className={`${styles.msgMetaRow} ${
                isUser ? styles.msgMetaRowRight : ""
              }`}
            >
              {message.timestamp > 0 && (
                <div
                  className={`${styles.msgTime} ${
                    isUser ? styles.msgTimeRight : ""
                  }`}
                >
                  {formatMessageTime(message.timestamp, serverTimezone)}
                  {!isUser && !isStreaming && speechText && (
                    <>
                      <CopyButton text={textContent} />
                      <button
                        className={`${styles.msgActionBtn} ${
                          speakingId === message.id
                            ? styles.msgActionBtnActive
                            : ""
                        }`}
                        onClick={(e) => {
                          e.stopPropagation();
                          speak(message.id, textContent);
                        }}
                        title={t("voice.readAloud", "朗读")}
                        type="button"
                      >
                        <Volume2 size={13} />
                      </button>
                    </>
                  )}
                  {!isUser && !isStreaming && onRegenerate && (
                    <button
                      className={styles.msgActionBtn}
                      onClick={() => onRegenerate(message.id)}
                      title={t("chat.regenerate", "重新生成")}
                      type="button"
                    >
                      <RotateCcw size={13} />
                    </button>
                  )}
                  {!isUser && !isStreaming && onForkAssistantMessage && (
                    <button
                      className={styles.msgActionBtn}
                      onClick={() => onForkAssistantMessage(message.id)}
                      disabled={forkDisabled}
                      title={
                        forkDisabled && forkDisabledHint
                          ? forkDisabledHint
                          : t("chat.forkFromHere")
                      }
                      type="button"
                      aria-label={t("chat.forkFromHere")}
                    >
                      <GitFork size={13} />
                    </button>
                  )}
                </div>
              )}
              {usageParts.length > 0 && (
                <div className={styles.msgUsage}>{usageParts.join(" / ")}</div>
              )}
            </div>
          )}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
