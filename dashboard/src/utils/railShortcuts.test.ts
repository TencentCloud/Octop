import { describe, expect, it } from "vitest";

import {
  isComposingKeyEvent,
  matchRailShortcut,
  railShortcutAria,
  railShortcutLabel,
  shouldIgnoreRailShortcut,
} from "./railShortcuts";

function key(overrides: Partial<Parameters<typeof matchRailShortcut>[0]> = {}) {
  return {
    key: "b",
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    ...overrides,
  };
}

describe("matchRailShortcut", () => {
  it("maps mod+B to the nav rail", () => {
    expect(matchRailShortcut(key({ metaKey: true }))).toBe("toggle-nav");
    expect(matchRailShortcut(key({ ctrlKey: true }))).toBe("toggle-nav");
  });

  it("maps mod+shift+B to the history rail", () => {
    expect(matchRailShortcut(key({ metaKey: true, shiftKey: true }))).toBe(
      "toggle-history",
    );
    expect(matchRailShortcut(key({ ctrlKey: true, shiftKey: true }))).toBe(
      "toggle-history",
    );
  });

  it("ignores plain letters, other keys and Alt chords", () => {
    // A bare "b" typed into the composer must stay a letter.
    expect(matchRailShortcut(key())).toBeNull();
    expect(matchRailShortcut(key({ shiftKey: true }))).toBeNull();
    // ⌥B is word-motion on macOS / a menu accelerator on Windows.
    expect(matchRailShortcut(key({ metaKey: true, altKey: true }))).toBeNull();
    expect(matchRailShortcut(key({ metaKey: true, key: "j" }))).toBeNull();
  });

  it("does not care about the letter's case", () => {
    expect(matchRailShortcut(key({ metaKey: true, key: "B" }))).toBe(
      "toggle-nav",
    );
  });
});

describe("shouldIgnoreRailShortcut", () => {
  it("stands down while a dialog is open", () => {
    expect(shouldIgnoreRailShortcut(null, true)).toBe(true);
  });

  it("leaves mod+B to rich-text surfaces", () => {
    expect(shouldIgnoreRailShortcut({ isContentEditable: true }, false)).toBe(
      true,
    );
    // Plain inputs and textareas do not own the chord — the composers are
    // textareas and the shortcut is expected to work while typing.
    expect(shouldIgnoreRailShortcut({ isContentEditable: false }, false)).toBe(
      false,
    );
    expect(shouldIgnoreRailShortcut(null, false)).toBe(false);
  });
});

describe("isComposingKeyEvent", () => {
  it("skips IME composition", () => {
    expect(isComposingKeyEvent({ isComposing: true })).toBe(true);
    // Safari clears isComposing before the keydown but keeps keyCode 229.
    expect(isComposingKeyEvent({ keyCode: 229 })).toBe(true);
    expect(isComposingKeyEvent({ isComposing: false, keyCode: 66 })).toBe(
      false,
    );
  });
});

describe("labels", () => {
  it("renders platform accelerators", () => {
    expect(railShortcutLabel("toggle-nav", true)).toBe("⌘B");
    expect(railShortcutLabel("toggle-history", true)).toBe("⇧⌘B");
    expect(railShortcutLabel("toggle-nav", false)).toBe("Ctrl+B");
    expect(railShortcutLabel("toggle-history", false)).toBe("Ctrl+Shift+B");
  });

  it("renders aria-keyshortcuts values", () => {
    expect(railShortcutAria("toggle-nav")).toBe("Meta+B");
    expect(railShortcutAria("toggle-history")).toBe("Meta+Shift+B");
  });
});
