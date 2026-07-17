import { useMemo } from "react";
import { ChevronRight, Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../hooks/useChat";
import {
  splitAssistantTurn,
  toAnswerOnlyMessage,
  countProcessStats,
  turnUsedBrowserTool,
} from "../utils/messageContent";
import { useAgent } from "../../../context/AgentContext";
import AssistantProcessSummary from "./AssistantProcessSummary";
import MessageBubble from "./MessageBubble";
import { ToolMediaStrip } from "./ToolMediaStrip";
import { collectTurnToolMedia } from "../../../utils/collectTurnToolMedia";
import styles from "../index.module.less";

interface AssistantTurnViewProps {
  messages: ChatMessage[];
  agentId?: string | null;
  isStreaming?: boolean;
  /** True while this assistant turn is still being generated (incl. between tool calls). */
  isTurnInProgress?: boolean;
  onRegenerate?: (messageId: string) => void;
  onEditUserMessage?: (messageId: string, newText: string) => void;
  onAcpPermissionSelect?: (message: string) => void;
  onHitlDecision?: (
    decisions: Array<{ type: string; message?: string }>,
  ) => void;
  onOpenBrowser?: () => void;
  onRunShellCommand?: (code: string) => void;
  shellCommandDisabled?: boolean;
  shellCommandDisabledTitle?: string;
  compactProcess?: boolean;
}

export default function AssistantTurnView({
  messages,
  agentId: agentIdProp,
  isStreaming = false,
  isTurnInProgress = false,
  onRegenerate,
  onEditUserMessage,
  onAcpPermissionSelect,
  onHitlDecision,
  onOpenBrowser,
  onRunShellCommand,
  shellCommandDisabled,
  shellCommandDisabledTitle,
  compactProcess = false,
}: AssistantTurnViewProps) {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const agentId = agentIdProp ?? activeAgentId;

  const hitlIdx = messages.findIndex((m) => m.hitlData);
  const hitlMessage = hitlIdx >= 0 ? messages[hitlIdx] : undefined;

  const preSplit = useMemo(() => {
    const preMessages = hitlIdx >= 0 ? messages.slice(0, hitlIdx) : messages;
    return splitAssistantTurn(preMessages);
  }, [messages, hitlIdx]);
  const postSplit = useMemo(() => {
    const postMessages = hitlIdx >= 0 ? messages.slice(hitlIdx + 1) : [];
    return splitAssistantTurn(postMessages);
  }, [messages, hitlIdx]);
  const answerSplit = hitlMessage ? postSplit : preSplit;

  const hasPreProcess = useMemo(() => {
    const { toolCount, thinkingCount } = countProcessStats(preSplit);
    return toolCount > 0 || thinkingCount > 0;
  }, [preSplit]);
  const hasPostProcess = useMemo(() => {
    const { toolCount, thinkingCount } = countProcessStats(postSplit);
    return toolCount > 0 || thinkingCount > 0;
  }, [postSplit]);

  const fullSplit = useMemo(() => splitAssistantTurn(messages), [messages]);

  const toolMedia = useMemo(
    () => collectTurnToolMedia(fullSplit, agentId),
    [fullSplit, agentId],
  );

  const turnStreaming =
    isTurnInProgress ||
    (isStreaming && messages.some((m) => m.status === "streaming"));
  const usedBrowser = turnUsedBrowserTool(fullSplit);
  const showOpenBrowser = usedBrowser && !!onOpenBrowser;
  const hasToolMedia =
    toolMedia.images.length > 0 ||
    toolMedia.videos.length > 0 ||
    toolMedia.files.length > 0;

  return (
    <div className={styles.assistantTurn}>
      {hasPreProcess && !compactProcess && (
        <div className={styles.processSummaryRow}>
          <AssistantProcessSummary
            split={preSplit}
            isStreaming={turnStreaming && !hitlMessage}
            onAcpPermissionSelect={onAcpPermissionSelect}
            hideToolMedia={hasToolMedia}
            agentId={agentId}
          />
        </div>
      )}
      {hitlMessage ? (
        <MessageBubble
          message={hitlMessage}
          onHitlDecision={onHitlDecision}
          groupPosition="only"
        />
      ) : null}
      {hasPostProcess && !compactProcess && (
        <div className={styles.processSummaryRow}>
          <AssistantProcessSummary
            split={postSplit}
            isStreaming={turnStreaming}
            onAcpPermissionSelect={onAcpPermissionSelect}
            hideToolMedia={hasToolMedia}
            agentId={agentId}
          />
        </div>
      )}
      {hasToolMedia && (
        <ToolMediaStrip
          images={toolMedia.images}
          videos={toolMedia.videos}
          files={toolMedia.files}
          agentId={agentId}
        />
      )}
      {answerSplit.answerMessage ? (
        <div className={styles.assistantTurnAnswer}>
          <MessageBubble
            message={toAnswerOnlyMessage(answerSplit.answerMessage)}
            onRegenerate={onRegenerate}
            onEditUserMessage={onEditUserMessage}
            groupPosition="only"
            onRunShellCommand={onRunShellCommand}
            shellCommandDisabled={shellCommandDisabled}
            shellCommandDisabledTitle={shellCommandDisabledTitle}
          />
        </div>
      ) : null}
      {showOpenBrowser && (
        <button
          type="button"
          className={`${styles.openBrowserPrompt} ${
            turnStreaming ? styles.openBrowserPromptActive : ""
          }`}
          onClick={onOpenBrowser}
          aria-label={t("chat.openBrowser")}
        >
          <Globe
            size={16}
            strokeWidth={2}
            className={styles.openBrowserPromptIcon}
            aria-hidden="true"
          />
          <span>{t("chat.openBrowser")}</span>
          <ChevronRight
            size={14}
            className={styles.openBrowserPromptArrow}
            aria-hidden="true"
          />
        </button>
      )}
    </div>
  );
}
