import { useMemo, useState } from "react";
import { Image, Button } from "antd";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  collectToolMediaFromToolData,
  parseStructuredToolOutput,
} from "../../../utils/toolMediaBlocks";
import { formatToolArguments } from "../../../utils/formatToolArguments";
import {
  useToolDisplayNames,
  resolveToolLabel,
} from "../../../pages/Chat/hooks/toolDisplayNames";
import {
  buildAcpPermissionRespondMessage,
  parseAcpPermissionPrompt,
} from "../../../utils/parseAcpPermission";
import { MessageFileCard } from "../../../pages/Chat/components/MessageFileCard";
import { parseKnowledgeCitations } from "../../../utils/parseKnowledgeCitations";
import styles from "../../../pages/Chat/index.module.less";
import type { ToolRenderProps } from "../types";

function ImageGallery({
  images,
}: {
  images: Array<{ url: string; filename?: string }>;
}) {
  return (
    <Image.PreviewGroup>
      {images.map((img, idx) => (
        <Image
          key={`${img.url}-${idx}`}
          src={img.url}
          alt={img.filename || "image"}
          style={{ maxWidth: 200, maxHeight: 160, objectFit: "cover" }}
        />
      ))}
    </Image.PreviewGroup>
  );
}

/**
 * Built-in fallback: collapsible tool chrome + media / text / ACP permission.
 * Preserves prior ``ToolDetailsInline`` behavior for tools without a plugin UI.
 */
export function DefaultToolRenderer({
  toolName,
  displayName: displayNameProp,
  args,
  output,
  isStreaming,
  hideMediaPreview = false,
  onAcpPermissionSelect,
  agentId = null,
  textFallback,
  data,
}: ToolRenderProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const displayName = useToolDisplayNames();

  const toolData = useMemo(
    () => ({
      name: toolName,
      arguments:
        typeof args === "string"
          ? args
          : args !== undefined
          ? JSON.stringify(args)
          : undefined,
      output,
    }),
    [toolName, args, output],
  );

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
  if (!formattedOutput && textFallback) {
    formattedOutput = textFallback;
  }
  if (!formattedOutput && typeof data === "string") {
    formattedOutput = data;
  }
  if (!formattedOutput && toolData.output) {
    formattedOutput = parseKnowledgeCitations(toolData.output).text;
    try {
      formattedOutput = JSON.stringify(JSON.parse(formattedOutput), null, 2);
    } catch {
      // keep as-is
    }
  } else if (formattedOutput) {
    formattedOutput = parseKnowledgeCitations(formattedOutput).text;
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
      toolName === "acp_runner"
        ? parseAcpPermissionPrompt(toolData.output, toolData.arguments)
        : null,
    [toolData.arguments, toolName, toolData.output],
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
          {resolveToolLabel(toolName, displayNameProp, displayName)}
        </code>
        <span className={styles.inlineToolStatus}>{statusLabel}</span>
        <ChevronRight
          size={14}
          className={`${styles.inlineToolChevron} ${
            expanded ? styles.inlineToolChevronOpen : ""
          }`}
        />
      </button>

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
