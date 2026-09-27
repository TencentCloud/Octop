import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import type { AssistantTurnSplit } from "../utils/messageContent";
import { countProcessStats } from "../utils/messageContent";
import { ToolDetailsInline } from "./MessageBubble";
import { useCollapseThinking } from "../hooks/useCollapseThinking";
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
  /** Team rooms default to collapsed thinking; solo stays expanded. */
  isTeam?: boolean;
  onAcpPermissionSelect?: (message: string) => void;
  hideToolMedia?: boolean;
  agentId?: string | null;
}

function resolveLiveProcessHint(
  split: AssistantTurnSplit,
  isStreaming: boolean,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | null {
  if (!isStreaming) return null;

  const runningTool = split.processSteps.find(
    (step) =>
      step.kind === "tool" &&
      step.message.status === "streaming" &&
      !step.message.toolData?.output,
  );
  if (runningTool && runningTool.kind === "tool") {
    return t("chat.processRunningTools", {
      defaultValue: "正在调用工具",
    });
  }

  const thinkingLive = split.processSteps.some(
    (step) => step.kind === "thinking" && step.item.isStreaming,
  );
  if (thinkingLive) {
    return t("chat.processThinkingLive", { defaultValue: "深度思考中" });
  }

  // Tool finished, next tokens not yet — keep the fold "alive" so it does
  // not look stuck on a static count between ReAct rounds.
  const hasProcess =
    split.tools.length > 0 ||
    split.thinkings.length > 0 ||
    split.processSteps.length > 0;
  if (hasProcess) {
    return t("chat.processOrganizing", { defaultValue: "整理结果中" });
  }

  return null;
}

/** Foldable thinking + plain tools only (no rich plugin UI). */
function AssistantProcessSummary({
  split,
  statsSplit,
  isStreaming = false,
  isTeam = false,
  onAcpPermissionSelect,
  hideToolMedia = false,
  agentId = null,
}: AssistantProcessSummaryProps) {
  const { t } = useTranslation();
  const [collapseThinking] = useCollapseThinking(isTeam);
  const [expanded, setExpanded] = useState(isStreaming && !collapseThinking);
  const prevStreaming = useRef(isStreaming);
  const prevCollapseThinking = useRef(collapseThinking);
  const { toolCount, thinkingCount } = useMemo(
    () => countProcessStats(statsSplit ?? split),
    [statsSplit, split],
  );
  const liveHint = useMemo(
    () => resolveLiveProcessHint(split, isStreaming, t),
    [split, isStreaming, t],
  );

  // Manual toggles hold until streaming or the display preference changes.
  // History stays collapsed, and generation respects the saved preference.
  // Only collapse when streaming ends — never flicker closed between tool rounds.
  useEffect(() => {
    if (
      prevStreaming.current === isStreaming &&
      prevCollapseThinking.current === collapseThinking
    )
      return;
    const wasStreaming = prevStreaming.current;
    prevStreaming.current = isStreaming;
    prevCollapseThinking.current = collapseThinking;
    if (isStreaming) {
      setExpanded(!collapseThinking);
      return;
    }
    if (wasStreaming) {
      setExpanded(false);
    } else if (collapseThinking) {
      setExpanded(false);
    }
  }, [isStreaming, collapseThinking]);

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
        className={`${styles.processSummaryToggle}${
          liveHint ? ` ${styles.processSummaryToggleLive}` : ""
        }`}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-busy={liveHint ? true : undefined}
      >
        <span className={styles.processSummaryText}>
          {liveHint ? (
            <span className={styles.processLiveHint} aria-live="polite">
              <span className={styles.thinkingDot} />
              <span className={styles.thinkingDot} />
              <span className={styles.thinkingDot} />
              <span className={styles.processLiveLabel}>{liveHint}</span>
            </span>
          ) : (
            summaryText
          )}
        </span>
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
