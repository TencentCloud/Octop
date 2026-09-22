import type { ChatMessage } from "../hooks/useChat";

export interface MessageGroup {
  isGroup: boolean;
  messages: ChatMessage[];
}

/** Roles that belong to an assistant ReAct turn (must not split the group). */
function isAssistantTurnRole(role: string): boolean {
  return role === "assistant" || role === "tool";
}

export function messageSpeakerId(message: ChatMessage): string {
  return (message.speakerAgentId || "").trim();
}

/** Speakers match when ids are equal. Empty ids match each other (1:1).
 *
 * In a 1:1 room, unlabeled tokens are the host — alias them to ``hostAgentId``.
 * Team rooms stamp every frame; do not alias there or two live streams merge.
 */
export function sameStreamingSpeaker(
  currentSpeakerId: string | undefined,
  incomingSpeakerId: string | undefined,
  hostAgentId?: string,
  teamRoom = false,
): boolean {
  const current = (currentSpeakerId || "").trim();
  const incoming = (incomingSpeakerId || "").trim();
  if (current && incoming) return current === incoming;
  if (!current && !incoming) return true;
  if (teamRoom) return false;
  return (
    isRoomHostSpeaker(currentSpeakerId, hostAgentId) &&
    isRoomHostSpeaker(incomingSpeakerId, hostAgentId)
  );
}

/** Unlabeled tokens are the 1:1 / legacy host. Stamped tokens match the room id. */
export function isRoomHostSpeaker(
  speakerId?: string,
  hostAgentId?: string,
): boolean {
  const incoming = (speakerId || "").trim();
  if (!incoming) return true;
  const host = (hostAgentId || "").trim();
  return Boolean(host && incoming === host);
}

/** History grouping may alias unlabeled rows to the room host. Live tokens must not. */
export function sameGroupedSpeaker(
  currentSpeakerId: string | undefined,
  incomingSpeakerId: string | undefined,
  hostAgentId?: string,
): boolean {
  if (sameStreamingSpeaker(currentSpeakerId, incomingSpeakerId, hostAgentId)) {
    return true;
  }
  return (
    isRoomHostSpeaker(currentSpeakerId, hostAgentId) &&
    isRoomHostSpeaker(incomingSpeakerId, hostAgentId)
  );
}

/** Last text bubble of this speaker in the current turn (before a later tool).
 *
 * Other speakers are skipped, not treated as a turn break — host and member
 * tokens interleave on the team room socket. Stop only at the last user
 * message so a later turn cannot resume the previous one.
 *
 * ``continueThroughTools`` only skips *in-flight* tools (no output yet). A
 * completed ``ask_agent`` is a turn break so the host wrap-up after members
 * reply opens a new bubble instead of appending to the dispatch text.
 */
export function findSpeakerTextToContinue(
  messages: ChatMessage[],
  speakerId?: string,
  hostAgentId?: string,
  options?: { continueThroughTools?: string[]; teamRoom?: boolean },
): number {
  const skipTools = new Set(options?.continueThroughTools ?? []);
  const teamRoom = Boolean(options?.teamRoom);
  let lastTool = -1;
  let lastText = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role === "user") break;
    if (message.role !== "assistant") continue;
    if (
      !sameStreamingSpeaker(
        message.speakerAgentId,
        speakerId,
        hostAgentId,
        teamRoom,
      )
    )
      continue;
    if (message.teamWrapup) continue;
    if (message.toolData) {
      const name = message.toolData.name || "";
      const inFlight = skipTools.has(name) && !message.toolData.output;
      if (inFlight) continue;
      if (lastTool < 0) lastTool = i;
      continue;
    }
    if (lastText < 0) lastText = i;
  }
  if (lastText < 0 || lastTool > lastText) return -1;
  return lastText;
}

/** True when a later visible reply from another speaker follows *targetIdx*. */
export function speakerTurnWasInterrupted(
  messages: ChatMessage[],
  targetIdx: number,
  speakerId?: string,
  hostAgentId?: string,
  teamRoom = false,
): boolean {
  for (let i = targetIdx + 1; i < messages.length; i++) {
    const message = messages[i];
    if (message.role === "user") break;
    if (message.role !== "assistant" || message.toolData) continue;
    if (
      sameStreamingSpeaker(
        message.speakerAgentId,
        speakerId,
        hostAgentId,
        teamRoom,
      )
    ) {
      continue;
    }
    if ((message.content || "").trim()) return true;
  }
  return false;
}

/**
 * Group consecutive assistant-turn messages for unified turn rendering.
 *
 * History loads often keep unmatched ``tool``-role rows between AI steps;
 * treating them as turn breakers produced multiple process summaries for one
 * user round-trip. Keep ``tool`` inside the assistant group.
 */
export function groupConsecutiveAssistantMessages(
  messages: ChatMessage[],
  hostAgentId?: string,
): MessageGroup[] {
  const groups: MessageGroup[] = [];
  let currentGroup: ChatMessage[] = [];

  for (const msg of messages) {
    if (isAssistantTurnRole(msg.role)) {
      if (
        currentGroup.length > 0 &&
        !sameGroupedSpeaker(
          currentGroup[currentGroup.length - 1].speakerAgentId,
          msg.speakerAgentId,
          hostAgentId,
        )
      ) {
        groups.push({ isGroup: true, messages: currentGroup });
        currentGroup = [];
      }
      if (
        currentGroup.length > 0 &&
        Boolean(msg.teamWrapup) !==
          currentGroup.some((item) => Boolean(item.teamWrapup))
      ) {
        groups.push({ isGroup: true, messages: currentGroup });
        currentGroup = [];
      }
      currentGroup.push(msg);
    } else {
      if (currentGroup.length > 0) {
        groups.push({ isGroup: true, messages: currentGroup });
        currentGroup = [];
      }
      groups.push({ isGroup: false, messages: [msg] });
    }
  }

  if (currentGroup.length > 0) {
    groups.push({ isGroup: true, messages: currentGroup });
  }

  return groups;
}
