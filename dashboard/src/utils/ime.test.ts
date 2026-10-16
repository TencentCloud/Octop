import type { KeyboardEvent } from "react";
import { describe, expect, it } from "vitest";
import { isImeComposing } from "./ime";

function keyEvent(init: {
  key?: string;
  keyCode?: number;
  isComposing?: boolean;
}): KeyboardEvent {
  return {
    key: init.key ?? "Enter",
    keyCode: init.keyCode ?? 13,
    nativeEvent: { isComposing: init.isComposing ?? false },
  } as unknown as KeyboardEvent;
}

describe("isImeComposing", () => {
  it("is true while the IME reports an active composition", () => {
    expect(isImeComposing(keyEvent({ isComposing: true }))).toBe(true);
  });

  it("is true for Safari's candidate-confirming Enter (keyCode 229)", () => {
    expect(isImeComposing(keyEvent({ keyCode: 229 }))).toBe(true);
  });

  it("is false for a plain Enter or Escape", () => {
    expect(isImeComposing(keyEvent({}))).toBe(false);
    expect(isImeComposing(keyEvent({ key: "Escape", keyCode: 27 }))).toBe(
      false,
    );
  });
});
