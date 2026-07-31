/**
 * Whether this assistant group is the live in-progress turn.
 *
 * After the user sends a new message, the previous assistant group is still
 * `lastAssistantGroupIndex` until the model replies — it must NOT be treated
 * as live, or its process summary re-expands and pushes the new user bubble
 * off-screen.
 */
export function isLiveAssistantTurn(opts: {
  isStreaming: boolean;
  groupIndex: number;
  lastAssistantGroupIndex: number;
  lastUserGroupIndex: number;
}): boolean {
  const {
    isStreaming,
    groupIndex,
    lastAssistantGroupIndex,
    lastUserGroupIndex,
  } = opts;
  return (
    isStreaming &&
    groupIndex === lastAssistantGroupIndex &&
    groupIndex > lastUserGroupIndex
  );
}
