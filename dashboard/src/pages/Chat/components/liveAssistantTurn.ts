/**
 * Whether this assistant group is part of the live in-progress turn.
 *
 * Any assistant group after the latest user message stays live while the
 * session is streaming so concurrent team speakers do not collapse their
 * process panels between tool rounds when another speaker is last in the list.
 *
 * After the user sends a new message, older assistant groups sit *before*
 * ``lastUserGroupIndex`` and must NOT be treated as live (or their process
 * summary re-expands and pushes the new user bubble off-screen).
 */
export function isLiveAssistantTurn(opts: {
  isStreaming: boolean;
  groupIndex: number;
  lastAssistantGroupIndex: number;
  lastUserGroupIndex: number;
}): boolean {
  const { isStreaming, groupIndex, lastUserGroupIndex } = opts;
  return isStreaming && groupIndex > lastUserGroupIndex;
}
