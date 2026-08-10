import { useMemo } from "react";
import { ChevronRight, FilePen, Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../hooks/useChat";
import {
  splitAssistantTurn,
  toAnswerOnlyMessage,
  countProcessStats,
  turnUsedBrowserTool,
  turnUsedFileTool,
} from "../utils/messageContent";
import { layoutAssistantTurnHitl } from "../utils/layoutAssistantTurnHitl";
import { useAgent } from "../../../context/AgentContext";
import { TodoProgressPanel } from "../../../components/TodoProgressPanel";
import {
  collectWriteTodosFromMessages,
  isWriteTodosToolName,
} from "../../../utils/parseWriteTodos";
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
  onEditFile?: () => void;
  onRunShellCommand?: (code: string) => void;
  shellCommandDisabled?: boolean;
  shellCommandDisabledTitle?: string;
  compactProcess?: boolean;
}

function hasProcessContent(
  split: ReturnType<typeof splitAssistantTurn>,
): boolean {
  const { toolCount, thinkingCount } = countProcessStats(split);
  return toolCount > 0 || thinkingCount > 0;
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
  onEditFile,
  onRunShellCommand,
  shellCommandDisabled,
  shellCommandDisabledTitle,
  compactProcess = false,
}: AssistantTurnViewProps) {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const agentId = agentIdProp ?? activeAgentId;

  const hitlLayout = useMemo(
    () => layoutAssistantTurnHitl(messages),
    [messages],
  );
  const hasPendingHitl = messages.some((m) => m.hitlData?.status === "pending");

  const segmentProcess = useMemo(
    () =>
      hitlLayout.segments.map((seg) => ({
        split: splitAssistantTurn(seg.processMessages),
        hitl: seg.hitlMessage,
      })),
    [hitlLayout],
  );
  const trailingSplit = useMemo(
    () => splitAssistantTurn(hitlLayout.trailingMessages),
    [hitlLayout],
  );

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
  const usedFileTool = turnUsedFileTool(fullSplit);
  const showEditFile = usedFileTool && !!onEditFile;
  const hasToolMedia =
    toolMedia.images.length > 0 ||
    toolMedia.videos.length > 0 ||
    toolMedia.files.length > 0;

  const todoItems = useMemo(
    () => collectWriteTodosFromMessages(messages),
    [messages],
  );
  const todoStreaming =
    turnStreaming &&
    messages.some(
      (m) => m.status === "streaming" && isWriteTodosToolName(m.toolData?.name),
    );

  const firstProcessSegmentIdx = compactProcess
    ? -1
    : segmentProcess.findIndex(({ split }) => hasProcessContent(split));
  const showTrailingProcess =
    !compactProcess && hasProcessContent(trailingSplit);
  const anyProcessShown = firstProcessSegmentIdx >= 0 || showTrailingProcess;

  const todoPanel =
    todoItems.length > 0 ? (
      <TodoProgressPanel
        items={todoItems}
        isStreaming={todoStreaming}
        followingProcessSummary={anyProcessShown}
      />
    ) : null;
  const todoAtTop = todoPanel && !anyProcessShown ? todoPanel : null;

  return (
    <div className={styles.assistantTurn}>
      {todoAtTop}
      {segmentProcess.map(({ split, hitl }, idx) => {
        const showProcess = !compactProcess && hasProcessContent(split);
        // Freeze process spinner while a pending approval card is open.
        const processStreaming =
          turnStreaming &&
          !hasPendingHitl &&
          idx === segmentProcess.length - 1 &&
          hitlLayout.trailingMessages.length === 0;
        return (
          <div key={hitl.id}>
            {showProcess ? (
              <>
                <div className={styles.processSummaryRow}>
                  <AssistantProcessSummary
                    split={split}
                    isStreaming={processStreaming}
                    onAcpPermissionSelect={onAcpPermissionSelect}
                    hideToolMedia={hasToolMedia}
                    agentId={agentId}
                  />
                </div>
                {todoPanel && idx === firstProcessSegmentIdx ? todoPanel : null}
              </>
            ) : null}
            <MessageBubble
              message={hitl}
              onHitlDecision={onHitlDecision}
              groupPosition="only"
            />
          </div>
        );
      })}
      {showTrailingProcess ? (
        <>
          <div className={styles.processSummaryRow}>
            <AssistantProcessSummary
              split={trailingSplit}
              isStreaming={turnStreaming && !hasPendingHitl}
              onAcpPermissionSelect={onAcpPermissionSelect}
              hideToolMedia={hasToolMedia}
              agentId={agentId}
            />
          </div>
          {todoPanel && firstProcessSegmentIdx < 0 ? todoPanel : null}
        </>
      ) : null}
      {hasToolMedia && (
        <ToolMediaStrip
          images={toolMedia.images}
          videos={toolMedia.videos}
          files={toolMedia.files}
          agentId={agentId}
        />
      )}
      {trailingSplit.answerMessage ? (
        <div className={styles.assistantTurnAnswer}>
          <MessageBubble
            message={toAnswerOnlyMessage(trailingSplit.answerMessage)}
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
      {showEditFile && (
        <button
          type="button"
          className={`${styles.openBrowserPrompt} ${
            turnStreaming ? styles.openBrowserPromptActive : ""
          }`}
          onClick={onEditFile}
          aria-label={t("chat.editFileCard", "编辑文件")}
        >
          <FilePen
            size={16}
            strokeWidth={2}
            className={styles.openBrowserPromptIcon}
            aria-hidden="true"
          />
          <span>{t("chat.editFileCard", "编辑文件")}</span>
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
