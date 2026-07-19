import { memo, useMemo, useState, useCallback, useRef } from "react";
import { Image, Button, message as antMessage } from "antd";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import {
  ChevronRight,
  Copy,
  Check,
  RotateCcw,
  Pencil,
  Volume2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatAttachment, ChatMessage } from "../hooks/useChat";
import type { ComposerTagLookups } from "./UserMessageComposerTags";
import UserMessageComposerTags from "./UserMessageComposerTags";
import { deriveMessageContent } from "../utils/messageContent";
import { useAuthImageSrc } from "../../../hooks/useAuthImageSrc";
import {
  agentAttachmentAccessUrl,
  collectToolMediaFromToolData,
  isDataUrl,
  parseStructuredToolOutput,
  workspacePathFromAccessUrl,
} from "../../../utils/toolMediaBlocks";
import { formatToolArguments } from "../../../utils/formatToolArguments";
import { formatMessageTime } from "../../../utils/formatMessageTime";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import {
  useToolDisplayNames,
  resolveToolLabel,
} from "../hooks/toolDisplayNames";
import {
  buildAcpPermissionRespondMessage,
  parseAcpPermissionPrompt,
} from "../../../utils/parseAcpPermission";
import { useVoiceOutputContext } from "../../../context/VoiceOutputContext";
import { prepareSpeechText } from "../../../utils/plainTextForSpeech";
import { MessageFileCard } from "./MessageFileCard";
import styles from "../index.module.less";

interface MessageBubbleProps {
  message: ChatMessage;
  agentId?: string | null;
  composerLookups?: ComposerTagLookups;
  onRegenerate?: (messageId: string) => void;
  onEditUserMessage?: (messageId: string, newText: string) => void;
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
  labels: { input: string; output: string; total: string },
): string[] {
  if (!usage) return [];

  const parts: string[] = [];
  if (typeof usage.input_tokens === "number") {
    parts.push(`${usage.input_tokens} ${labels.input}`);
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
  const { src, loadState, setSrc } = useAuthImageSrc(url, filename);
  const retried = useRef(false);

  const handleError = useCallback(() => {
    if (retried.current) return;
    retried.current = true;

    if (isDataUrl(url)) return;

    const path = workspacePath || workspacePathFromAccessUrl(url);
    if (!path || !agentId) return;

    setSrc(agentAttachmentAccessUrl(agentId, path, mediaType));
  }, [url, agentId, workspacePath, mediaType, setSrc]);

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
    try {
      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(text);
        } catch {
          // Clipboard API can fail in PWA standalone mode when the document
          // loses focus briefly on button press — fall through to execCommand.
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.left = "-999999px";
          ta.style.top = "-999999px";
          document.body.appendChild(ta);
          ta.focus();
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-999999px";
        ta.style.top = "-999999px";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      setCopied(true);
      antMessage.success(t("common.copied"));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      antMessage.error(t("common.copyFailed"));
    }
  }, [text, t]);

  return (
    <button className={styles.msgCopyBtn} onClick={handleCopy} title="Copy">
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

export function ToolDetailsInline({
  toolData,
  isStreaming,
  onAcpPermissionSelect,
  hideMediaPreview = false,
  agentId = null,
}: {
  toolData: NonNullable<ChatMessage["toolData"]>;
  isStreaming: boolean;
  onAcpPermissionSelect?: (message: string) => void;
  hideMediaPreview?: boolean;
  agentId?: string | null;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const displayName = useToolDisplayNames();

  const structuredOutput = useMemo(() => {
    const parsed = parseStructuredToolOutput(toolData.output, agentId);
    const media = collectToolMediaFromToolData(toolData, agentId);
    return {
      images: media.images,
      videos: media.videos,
      files: parsed.files,
      textOutput: parsed.textOutput,
    };
  }, [toolData, agentId]);

  const formattedArgs = useMemo(
    () => formatToolArguments(toolData.arguments || ""),
    [toolData.arguments],
  );

  let formattedOutput = structuredOutput.textOutput;
  if (!formattedOutput && toolData.output) {
    formattedOutput = toolData.output;
    try {
      formattedOutput = JSON.stringify(JSON.parse(formattedOutput), null, 2);
    } catch {
      // keep as-is
    }
  }

  const hasMediaPreview =
    structuredOutput.images.length > 0 || structuredOutput.videos.length > 0;
  const hasResult = toolData.output !== undefined;
  const completed = hasResult || (!isStreaming && hasMediaPreview);
  const mediaOnly =
    completed &&
    hasMediaPreview &&
    !structuredOutput.textOutput &&
    structuredOutput.files.length === 0;
  const acpPermission = useMemo(
    () =>
      toolData.name === "acp_runner"
        ? parseAcpPermissionPrompt(toolData.output, toolData.arguments)
        : null,
    [toolData.arguments, toolData.name, toolData.output],
  );
  const statusLabel = completed
    ? t("common.done", "Done")
    : isStreaming
    ? t("common.running", "Running")
    : t("common.pending", "Pending");

  return (
    <div className={styles.inlineToolBlock}>
      <button
        type="button"
        className={styles.inlineToolSummary}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className={styles.inlineToolLabel}>
          {t("chatUsage.tool", "Tool")}
        </span>
        <code className={styles.inlineToolName}>
          {resolveToolLabel(toolData.name, toolData.displayName, displayName)}
        </code>
        <span className={styles.inlineToolStatus}>{statusLabel}</span>
        <ChevronRight
          size={14}
          className={`${styles.inlineToolChevron} ${
            expanded ? styles.inlineToolChevronOpen : ""
          }`}
        />
      </button>

      {/* Media previews stay outside the collapsible details (unless shown on turn strip). */}
      {!hideMediaPreview && structuredOutput.images.length > 0 && (
        <div className={styles.inlineToolMediaPreview}>
          <ImageGallery images={structuredOutput.images} />
        </div>
      )}
      {!hideMediaPreview && structuredOutput.videos.length > 0 && (
        <div className={styles.inlineToolMediaPreview}>
          {structuredOutput.videos.map((video, idx) => (
            <video
              key={`${video.url}-${idx}`}
              className={styles.toolMediaVideo}
              src={video.url}
              controls
              preload="metadata"
              playsInline
            />
          ))}
        </div>
      )}
      {!hideMediaPreview && structuredOutput.files.length > 0 && (
        <div className={styles.inlineToolMediaPreview}>
          <div className={styles.messageFiles}>
            {structuredOutput.files.map((file, idx) => (
              <MessageFileCard
                key={`${file.url}-${idx}`}
                url={file.url}
                filename={file.filename}
                agentId={agentId}
              />
            ))}
          </div>
        </div>
      )}

      {expanded && (
        <div className={styles.inlineToolDetails}>
          {toolData.arguments !== undefined && (
            <div className={styles.inlineToolSection}>
              <div className={styles.inlineToolSectionLabel}>
                {t("chatUsage.arguments", "Arguments")}
              </div>
              <pre className={styles.inlineToolCode}>{formattedArgs}</pre>
            </div>
          )}
          {(hasResult || (!isStreaming && hasMediaPreview)) && !mediaOnly && (
            <div className={styles.inlineToolSection}>
              <div className={styles.inlineToolSectionLabel}>
                {t("chatUsage.result", "Result")}
              </div>
              {formattedOutput ? (
                <pre className={styles.inlineToolCode}>{formattedOutput}</pre>
              ) : (
                <pre className={styles.inlineToolCode}>
                  [{t("chatUsage.mediaOutput", "Media output")}]
                </pre>
              )}
            </div>
          )}
          {acpPermission && onAcpPermissionSelect && !isStreaming && (
            <div className={styles.inlineToolSection}>
              <div className={styles.inlineToolSectionLabel}>
                {t("acp.chatPermissionTitle", "外部 Agent 需要权限确认")}
              </div>
              <p className={styles.inlineToolHint}>{acpPermission.title}</p>
              <div className={styles.acpPermissionActions}>
                {acpPermission.options.map((opt) => (
                  <Button
                    key={opt.id}
                    size="small"
                    type="default"
                    onClick={() =>
                      onAcpPermissionSelect(
                        buildAcpPermissionRespondMessage(
                          acpPermission.runner,
                          opt.id,
                        ),
                      )
                    }
                  >
                    {opt.title}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  agentId = null,
  composerLookups,
  onRegenerate,
  onEditUserMessage,
  onHitlDecision,
  compact,
  groupPosition = "only",
  onRunShellCommand,
  shellCommandDisabled,
  shellCommandDisabledTitle,
}: MessageBubbleProps) {
  const { t } = useTranslation();
  const serverTimezone = useServerTimezone();

  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(message.content);

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
  const usageParts = useMemo(
    () =>
      formatTokenUsage(message.usage, {
        input: t("chatUsage.input"),
        output: t("chatUsage.output"),
        total: t("chatUsage.total"),
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
  const isError = message.status === "error";
  const isStreaming = message.status === "streaming";
  const hasToolData = !!message.toolData;
  const attachments = message.attachments || [];
  const imageAttachments = attachments.filter(
    (attachment) => attachment.kind === "image",
  );
  const fileAttachments = attachments.filter(
    (attachment) => attachment.kind === "file",
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
            {!isEditing && message.content && (
              <CopyButton text={message.content} />
            )}
            {!isEditing && onEditUserMessage && (
              <button
                className={styles.msgActionBtn}
                onClick={() => {
                  setEditText(message.content);
                  setIsEditing(true);
                }}
                title={t("common.edit")}
                type="button"
              >
                <Pencil size={13} />
              </button>
            )}
            {isEditing ? (
              <div className={styles.editArea}>
                <textarea
                  className={styles.editTextarea}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  autoFocus
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
                  {fileAttachments.length > 0 && (
                    <FileAttachmentList
                      files={fileAttachments}
                      agentId={agentId}
                    />
                  )}
                  {message.content && <div>{message.content}</div>}
                </div>
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
                {textContent && (
                  <div className={styles.errorMessageBody}>{textContent}</div>
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
            ) : (
              <div className={`${styles.assistantText} ${groupCls}`}>
                {imageAttachments.length > 0 && (
                  <ImageGallery images={imageAttachments} agentId={agentId} />
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
                {isStreaming && textContent && (
                  <span className={styles.cursor} />
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
