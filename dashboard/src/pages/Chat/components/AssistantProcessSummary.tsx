import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import type { AssistantTurnSplit } from "../utils/messageContent";
import { countProcessStats } from "../utils/messageContent";
import { ToolDetailsInline } from "./MessageBubble";
import styles from "../index.module.less";

interface AssistantProcessSummaryProps {
  /** Fold body: thinking + plain tools (pinned rich-UI tools excluded). */
  split: AssistantTurnSplit;
  /**
   * Full turn used for the summary counts. Pinned plugin UIs are siblings of
   * this fold, but they still count as tool calls in the headline.
   */
  statsSplit?: AssistantTurnSplit;
  isStreaming?: boolean;
  onAcpPermissionSelect?: (message: string) => void;
  hideToolMedia?: boolean;
  agentId?: string | null;
}

/** Foldable thinking + plain tools only (no rich plugin UI). */
function AssistantProcessSummary({
  split,
  statsSplit,
  isStreaming = false,
  onAcpPermissionSelect,
  hideToolMedia = false,
  agentId = null,
}: AssistantProcessSummaryProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(isStreaming);
  const prevStreaming = useRef(isStreaming);
  const { toolCount, thinkingCount } = useMemo(
    () => countProcessStats(statsSplit ?? split),
    [statsSplit, split],
  );

  // Follow the stream: expand while generating, collapse once the turn ends.
  // Manual toggles hold until the next streaming transition; history renders
  // with isStreaming=false and therefore stays collapsed.
  useEffect(() => {
    if (prevStreaming.current === isStreaming) return;
    prevStreaming.current = isStreaming;
    setExpanded(isStreaming);
  }, [isStreaming]);

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
