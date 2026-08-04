/**
 * Decide how to react to a server ``turn_status`` frame after subscribe.
 */

export type TurnStatusAction = "idle" | "expect_stream";

export function turnStatusAction(active: boolean): TurnStatusAction {
  return active ? "expect_stream" : "idle";
}
