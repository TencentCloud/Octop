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

/**
 * Whether this assistant group's process fold should show a live hint.
 *
 * ``isTurnInProgress`` already limits the session-busy flag to groups after
 * the latest user. A live speaker id of "" matches every unlabeled historical
 * bubble, so speaker liveness and a leftover streaming row only count for
 * the turn after that user.
 */
export function isAssistantProcessLive(opts: {
  isTurnInProgress: boolean;
  afterLatestUser: boolean;
  hasStreamingMessage: boolean;
  speakerLive: boolean;
}): boolean {
  return (
    opts.isTurnInProgress ||
    (opts.afterLatestUser && (opts.hasStreamingMessage || opts.speakerLive))
  );
}
