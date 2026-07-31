import { memo, useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import type { AssistantTurnSplit } from "../utils/messageContent";
import { countProcessStats } from "../utils/messageContent";
import { ToolDetailsInline } from "./MessageBubble";
import styles from "../index.module.less";

interface AssistantProcessSummaryProps {
  split: AssistantTurnSplit;
  isStreaming?: boolean;
  onAcpPermissionSelect?: (message: string) => void;
  /** When true, tool inline blocks skip image/video (shown on the turn strip). */
  hideToolMedia?: boolean;
  agentId?: string | null;
}

function AssistantProcessSummary({
  split,
  isStreaming = false,
  onAcpPermissionSelect,
  hideToolMedia = false,
  agentId = null,
}: AssistantProcessSummaryProps) {
  const { t } = useTranslation();
  // Always collapsed by default — tools/thinking stay merged until the user opens them.
  const [expanded, setExpanded] = useState(false);
  const { toolCount, thinkingCount } = useMemo(
    () => countProcessStats(split),
    [split],
  );

  if (toolCount === 0 && thinkingCount === 0) return null;

  const summaryText =
    toolCount > 0 && thinkingCount > 0
      ? t("chat.processSummary", {
          tools: toolCount,
          thinking: thinkingCount,
          defaultValue: "已调用 {{tools}} 次工具，{{thinking}} 次深度思考",
        })
      : toolCount > 0
        ? t("chat.processSummaryToolsOnly", {
            tools: toolCount,
            defaultValue: "已调用 {{tools}} 次工具",
          })
        : t("chat.processSummaryThinkingOnly", {
            thinking: thinkingCount,
            defaultValue: "{{thinking}} 次深度思考",
          });

  return (
    <div className={styles.processSummary}>
      <button
        type="button"
        className={styles.processSummaryToggle}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className={styles.processSummaryText}>{summaryText}</span>
        <ChevronRight
          size={14}
          className={`${styles.processSummaryChevron} ${
            expanded ? styles.processSummaryChevronOpen : ""
          }`}
        />
      </button>
      {expanded && (
        <div className={styles.processSummaryBody}>
          {split.processSteps.map((step, idx) =>
            step.kind === "thinking" ? (
              <div
                key={`${step.item.messageId}-thinking-${idx}`}
                className={styles.processThinkingItem}
              >
                <Markdown
                  content={step.item.content}
                  isStreaming={!!step.item.isStreaming && isStreaming}
                />
              </div>
            ) : (
              <div key={step.message.id} className={styles.processToolItem}>
                {step.message.toolData && (
                  <ToolDetailsInline
                    toolData={step.message.toolData}
                    isStreaming={
                      step.message.status === "streaming" && isStreaming
                    }
                    onAcpPermissionSelect={onAcpPermissionSelect}
                    hideMediaPreview={hideToolMedia}
                    agentId={agentId}
                  />
                )}
              </div>
            ),
          )}
        </div>
      )}
    </div>
  );
}

export default memo(AssistantProcessSummary);
