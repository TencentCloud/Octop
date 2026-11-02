import type { KeyboardEvent } from "react";

/**
 * True while an input method (Chinese / Japanese / Korean IME) is composing.
 *
 * The Enter that confirms a candidate still reaches `keydown` as
 * `key === "Enter"` on macOS, and Safari clears `isComposing` before that
 * keydown but keeps `keyCode` 229. Enter / Escape handlers that submit or
 * cancel must skip these events, or half-typed pinyin gets submitted and an
 * Escape meant for the candidate window discards the edit.
 */
export function isImeComposing(event: KeyboardEvent): boolean {
  return event.nativeEvent.isComposing || event.keyCode === 229;
}
