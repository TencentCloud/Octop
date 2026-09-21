import { useMemo } from "react";
import type { ChatMessage } from "../hooks/useChat";
import type { AssistantTurnSplit } from "../utils/messageContent";
import { countProcessStats } from "../utils/messageContent";
import { partitionPinnedTools } from "../../../plugins/toolRenderers/isPinnedToolUi";
import { useToolRendererVersion } from "../../../plugins/toolRenderers";
import AssistantProcessSummary from "./AssistantProcessSummary";
import { ToolDetailsInline } from "./MessageBubble";
import { ExpertMessageAvatar } from "./MessageSender";
import { useAgent } from "../../../context/AgentContext";
import { isTeamAgent, isTeamHostSpeaker } from "../../../utils/teamAgent";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

interface TurnProcessBlocksProps {
  split: AssistantTurnSplit;
  isStreaming: boolean;
  onAcpPermissionSelect?: (message: string) => void;
  hideToolMedia: boolean;
  agentId: string | null;
  /** One expert avatar per turn — only the first process row should show it. */
  showAvatar?: boolean;
}

function hasFoldContent(split: AssistantTurnSplit): boolean {
  const { toolCount, thinkingCount } = countProcessStats(split);
  return toolCount > 0 || thinkingCount > 0;
}

/** Process summary (fold) and rich tool UIs as **sibling** blocks — not nested. */
export function TurnProcessBlocks({
  split,
  isStreaming,
  onAcpPermissionSelect,
  hideToolMedia,
  agentId,
  showAvatar = false,
}: TurnProcessBlocksProps) {
  const { t } = useTranslation();
  const { agents, activeAgent } = useAgent();
  const isTeamRoom = isTeamAgent(activeAgent);
  const hostSpeaker = isTeamHostSpeaker(
    isTeamRoom,
    agentId,
    activeAgent?.agent_id,
  );
  const expert =
    (agentId && agents.find((item) => item.agent_id === agentId)) ||
    (!isTeamRoom || hostSpeaker ? activeAgent : undefined);
  const avatarTooltip = hostSpeaker
    ? t("chat.teamHostHover", { name: activeAgent?.name || expert?.name || "" })
    : expert?.name || undefined;
  const avatarProfileId = hostSpeaker
    ? activeAgent?.agent_id
    : agentId || undefined;
  const rendererVersion = useToolRendererVersion();
  const { pinned, folded } = useMemo(
    () => partitionPinnedTools(split),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [split, rendererVersion],
  );
  const showFold = hasFoldContent(folded);

  if (!showFold && pinned.length === 0) return null;

  return (
    <>
      {showFold ? (
        <div className={styles.processSummaryRow}>
          {showAvatar && (expert || avatarProfileId) ? (
            <div className={styles.avatarCol}>
              <ExpertMessageAvatar
                name={expert?.name || avatarProfileId}
                color={expert?.color}
                iconName={expert?.icon_name}
                iconUrl={expert?.icon_url}
                tooltip={avatarTooltip}
                profileAgentId={avatarProfileId}
              />
            </div>
          ) : null}
          <AssistantProcessSummary
            split={folded}
            statsSplit={split}
            isStreaming={isStreaming}
            onAcpPermissionSelect={onAcpPermissionSelect}
            hideToolMedia={hideToolMedia}
            agentId={agentId}
          />
        </div>
      ) : null}
      {pinned.length > 0 ? (
        <div className={styles.turnInset}>
          <div className={styles.pinnedToolResults} data-octop-pinned-tools="">
            {pinned.map((message: ChatMessage) =>
              message.toolData ? (
                <div key={message.id} className={styles.pinnedToolResultItem}>
                  <ToolDetailsInline
                    toolData={message.toolData}
                    isStreaming={message.status === "streaming" && isStreaming}
                    onAcpPermissionSelect={onAcpPermissionSelect}
                    hideMediaPreview={hideToolMedia}
                    agentId={agentId}
                  />
                </div>
              ) : null,
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

export function turnHasVisibleProcess(split: AssistantTurnSplit): boolean {
  const { pinned, folded } = partitionPinnedTools(split);
  return hasFoldContent(folded) || pinned.length > 0;
}

/** True when the foldable「已调用 N 次工具 / 深度思考」row will render. */
export function turnHasProcessSummary(split: AssistantTurnSplit): boolean {
  return hasFoldContent(partitionPinnedTools(split).folded);
}
