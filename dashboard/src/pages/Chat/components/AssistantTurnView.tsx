import { useMemo } from "react";
import { ChevronRight, FilePen, Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { HitlDecisionHandler } from "../../../api/types/hitl";
import type { ChatMessage } from "../hooks/useChat";
import {
  splitAssistantTurn,
  toAnswerOnlyMessage,
  turnUsedBrowserTool,
  turnUsedFileTool,
} from "../utils/messageContent";
import { isWriteToolName } from "../constants";
import { collectChatFilePaths } from "../hooks/useChatFileDetection";
import { layoutAssistantTurnHitl } from "../utils/layoutAssistantTurnHitl";
import { useAgent } from "../../../context/AgentContext";
import { TodoProgressPanel } from "../../../components/TodoProgressPanel";
import {
  collectWriteTodosFromMessages,
  isWriteTodosToolName,
} from "../../../utils/parseWriteTodos";
import MessageBubble from "./MessageBubble";
import { ToolMediaStrip } from "./ToolMediaStrip";
import {
  TurnProcessBlocks,
  turnHasProcessSummary,
  turnHasVisibleProcess,
} from "./TurnProcessBlocks";
import { collectTurnToolMedia } from "../../../utils/collectTurnToolMedia";
import { collectTurnKnowledgeCitations } from "../../../utils/collectTurnKnowledgeCitations";
import { KnowledgeCitationsStrip } from "./KnowledgeCitationsStrip";
import { messageSpeakerId } from "../utils/messageGrouping";
import styles from "../index.module.less";

interface AssistantTurnViewProps {
  messages: ChatMessage[];
  agentId?: string | null;
  isStreaming?: boolean;
  /** True while this assistant turn is still being generated (incl. between tool calls). */
  isTurnInProgress?: boolean;
  /**
   * Speakers still generating in the session store (survives tool gaps after
   * the composer unlocks). Empty string = unlabeled host.
   */
  liveSpeakers?: ReadonlyArray<string>;
  onRegenerate?: (messageId: string) => void;
  onEditUserMessage?: (messageId: string, newText: string) => void;
  onForkAssistantMessage?: (messageId: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
  onAcpPermissionSelect?: (message: string) => void;
  onHitlDecision?: HitlDecisionHandler;
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
  return turnHasVisibleProcess(split);
}

/** True when any message in this turn belongs to a still-live speaker. */
function turnHasLiveSpeaker(
  messages: ChatMessage[],
  liveSpeakers: ReadonlyArray<string>,
): boolean {
  if (liveSpeakers.length === 0) return false;
  const live = new Set(liveSpeakers);
  for (const message of messages) {
    if (live.has(messageSpeakerId(message))) return true;
  }
  return false;
}

export default function AssistantTurnView({
  messages,
  agentId: agentIdProp,
  isTurnInProgress = false,
  liveSpeakers = [],
  onRegenerate,
  onEditUserMessage,
  onForkAssistantMessage,
  forkDisabled,
  forkDisabledHint,
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
  const speakerAgentId =
    messages.map((item) => messageSpeakerId(item)).find(Boolean) || agentId;

  const speakerLive = turnHasLiveSpeaker(messages, liveSpeakers);
  const hasStreamingMsg = messages.some((m) => m.status === "streaming");
  const turnStreaming = isTurnInProgress || hasStreamingMsg || speakerLive;

  const hitlLayout = useMemo(
    () => layoutAssistantTurnHitl(messages),
    [messages],
  );
  const hasPendingHitl = messages.some((m) => m.hitlData?.status === "pending");

  const splitOpts = useMemo(
    () => ({ joinAnswerFragments: turnStreaming }),
    [turnStreaming],
  );

  const segmentProcess = useMemo(
    () =>
      hitlLayout.segments.map((seg) => ({
        split: splitAssistantTurn(seg.processMessages, splitOpts),
        hitl: seg.hitlMessage,
      })),
    [hitlLayout, splitOpts],
  );
  const trailingSplit = useMemo(
    () => splitAssistantTurn(hitlLayout.trailingMessages, splitOpts),
    [hitlLayout, splitOpts],
  );

  const fullSplit = useMemo(
    () => splitAssistantTurn(messages, splitOpts),
    [messages, splitOpts],
  );

  const toolMedia = useMemo(
    () => collectTurnToolMedia(fullSplit, speakerAgentId),
    [fullSplit, speakerAgentId],
  );
  const knowledgeCitations = useMemo(
    () => collectTurnKnowledgeCitations(fullSplit),
    [fullSplit],
  );

  const usedBrowser = turnUsedBrowserTool(fullSplit);
  const showOpenBrowser = usedBrowser && !!onOpenBrowser;
  const usedFileTool = turnUsedFileTool(fullSplit);
  const showEditFile = usedFileTool && !!onEditFile;
  const turnFileCount = useMemo(() => {
    const fromPaths = collectChatFilePaths(messages, agentId).length;
    if (fromPaths > 0) return fromPaths;
    return (fullSplit.tools ?? []).filter((msg) =>
      isWriteToolName(msg.toolData?.name),
    ).length;
  }, [messages, agentId, fullSplit.tools]);
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
  const firstSummaryIdx = compactProcess
    ? -1
    : segmentProcess.findIndex(({ split }) => turnHasProcessSummary(split));
  const showTrailingProcess =
    !compactProcess && hasProcessContent(trailingSplit);
  const trailingHasSummary =
    !compactProcess && turnHasProcessSummary(trailingSplit);
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

  const isWrapupTurn = messages.some((item) => item.teamWrapup);

  return (
    <div className={styles.assistantTurn}>
      {todoAtTop ? <div className={styles.turnInset}>{todoAtTop}</div> : null}
      {segmentProcess.map(({ split, hitl }, idx) => {
        const showProcess = !compactProcess && hasProcessContent(split);
        // Freeze process spinner while a pending approval card is open.
        const processStreaming =
          turnStreaming &&
          !hasPendingHitl &&
          idx === segmentProcess.length - 1 &&
          hitlLayout.trailingMessages.length === 0;
        return (
          <div key={hitl.id} className={styles.hitlSegment}>
            {showProcess ? (
              <>
                <TurnProcessBlocks
                  split={split}
                  isStreaming={processStreaming}
                  onAcpPermissionSelect={onAcpPermissionSelect}
                  hideToolMedia={hasToolMedia}
                  agentId={speakerAgentId}
                  showAvatar={idx === firstSummaryIdx}
                />
                {todoPanel && idx === firstProcessSegmentIdx ? (
                  <div className={styles.turnInset}>{todoPanel}</div>
                ) : null}
              </>
            ) : null}
            <MessageBubble
              message={hitl}
              agentId={agentId}
              onHitlDecision={onHitlDecision}
              groupPosition="only"
            />
          </div>
        );
      })}
      {showTrailingProcess ? (
        <>
          <TurnProcessBlocks
            split={trailingSplit}
            isStreaming={turnStreaming && !hasPendingHitl}
            onAcpPermissionSelect={onAcpPermissionSelect}
            hideToolMedia={hasToolMedia}
            agentId={speakerAgentId}
            showAvatar={firstSummaryIdx < 0 && trailingHasSummary}
          />
          {todoPanel && firstProcessSegmentIdx < 0 ? (
            <div className={styles.turnInset}>{todoPanel}</div>
          ) : null}
        </>
      ) : null}
      {hasToolMedia && (
        <div className={styles.turnInset}>
          <ToolMediaStrip
            images={toolMedia.images}
            videos={toolMedia.videos}
            files={toolMedia.files}
            agentId={speakerAgentId}
          />
        </div>
      )}
      {trailingSplit.answerMessage ? (
        <div
          className={`${styles.assistantTurnAnswer}${
            isWrapupTurn ? ` ${styles.teamWrapupTurn}` : ""
          }`}
        >
          {isWrapupTurn ? (
            <span className={styles.teamWrapupBadge}>
              {t("chat.teamWrapupBadge", { defaultValue: "主持人总结" })}
            </span>
          ) : null}
          <MessageBubble
            message={toAnswerOnlyMessage(trailingSplit.answerMessage)}
            agentId={agentId}
            showAvatar={firstSummaryIdx < 0 && !trailingHasSummary}
            onRegenerate={onRegenerate}
            onEditUserMessage={onEditUserMessage}
            onForkAssistantMessage={onForkAssistantMessage}
            forkDisabled={forkDisabled}
            forkDisabledHint={forkDisabledHint}
            groupPosition="only"
            onRunShellCommand={onRunShellCommand}
            shellCommandDisabled={shellCommandDisabled}
            shellCommandDisabledTitle={shellCommandDisabledTitle}
          />
        </div>
      ) : null}
      {knowledgeCitations.length > 0 ? (
        <div className={styles.turnInset}>
          <KnowledgeCitationsStrip citations={knowledgeCitations} />
        </div>
      ) : null}
      {showOpenBrowser && (
        <div className={styles.turnInset}>
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
        </div>
      )}
      {showEditFile && (
        <div className={styles.turnInset}>
          <button
            type="button"
            className={`${styles.openBrowserPrompt} ${
              turnStreaming ? styles.openBrowserPromptActive : ""
            }`}
            onClick={onEditFile}
            aria-label={t("chat.editFileCard", {
              count: Math.max(turnFileCount, 1),
              defaultValue: "编辑了{{count}}个文件",
            })}
          >
            <FilePen
              size={16}
              strokeWidth={2}
              className={styles.openBrowserPromptIcon}
              aria-hidden="true"
            />
            <span>
              {t("chat.editFileCard", {
                count: Math.max(turnFileCount, 1),
                defaultValue: "编辑了{{count}}个文件",
              })}
            </span>
            <ChevronRight
              size={14}
              className={styles.openBrowserPromptArrow}
              aria-hidden="true"
            />
          </button>
        </div>
      )}
    </div>
  );
}
