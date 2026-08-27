/** Stable dock tab id for a tool call's plugin UI panel. */
export function dockToolUiTabId(callId: string): string {
  return `toolUi:${callId}`;
}
