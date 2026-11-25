import { fireEvent, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useRailShortcuts } from "./useRailShortcuts";

function press(init: KeyboardEventInit) {
  fireEvent.keyDown(window, init);
}

function setup() {
  const onToggleNav = vi.fn();
  const onToggleHistory = vi.fn();
  renderHook(() => useRailShortcuts({ onToggleNav, onToggleHistory }));
  return { onToggleNav, onToggleHistory };
}

describe("useRailShortcuts", () => {
  it("toggles the nav rail on mod+B", () => {
    const { onToggleNav, onToggleHistory } = setup();
    press({ key: "b", ctrlKey: true });
    expect(onToggleNav).toHaveBeenCalledTimes(1);
    expect(onToggleHistory).not.toHaveBeenCalled();
  });

  it("toggles the history rail on mod+shift+B", () => {
    const { onToggleNav, onToggleHistory } = setup();
    press({ key: "B", metaKey: true, shiftKey: true });
    expect(onToggleHistory).toHaveBeenCalledTimes(1);
    expect(onToggleNav).not.toHaveBeenCalled();
  });

  it("leaves plain typing alone", () => {
    const { onToggleNav, onToggleHistory } = setup();
    press({ key: "b" });
    expect(onToggleNav).not.toHaveBeenCalled();
    expect(onToggleHistory).not.toHaveBeenCalled();
  });

  it("stands down while a dialog is open", () => {
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    document.body.appendChild(dialog);
    const { onToggleNav } = setup();
    press({ key: "b", ctrlKey: true });
    expect(onToggleNav).not.toHaveBeenCalled();
    dialog.remove();
  });

  it("ignores key repeat", () => {
    const { onToggleNav } = setup();
    press({ key: "b", ctrlKey: true, repeat: true });
    expect(onToggleNav).not.toHaveBeenCalled();
  });

  it("calls the latest handler without rebinding", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ handler }: { handler: () => void }) =>
        useRailShortcuts({ onToggleNav: handler, onToggleHistory: vi.fn() }),
      { initialProps: { handler: first } },
    );
    rerender({ handler: second });
    press({ key: "b", ctrlKey: true });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
