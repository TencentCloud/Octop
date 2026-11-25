import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useBrowserKeyboard } from "./useBrowserKeyboard";

function setup(enabled = true) {
  const sendEvent = vi.fn((_event: Record<string, unknown>) => true);
  function Harness() {
    const { inputRef, focusInput, ...events } = useBrowserKeyboard(
      enabled,
      sendEvent,
    );
    return (
      <>
        <canvas tabIndex={0} onFocus={focusInput} />
        <textarea aria-label="Remote input" ref={inputRef} {...events} />
        <input aria-label="Address" />
      </>
    );
  }
  const view = render(<Harness />);
  const input = screen.getByLabelText("Remote input") as HTMLTextAreaElement;
  return { ...view, input, sendEvent };
}

describe("remote browser keyboard", () => {
  it("focuses a text control and leaves printable keys to native input", () => {
    const { container, input, sendEvent } = setup();
    act(() => container.querySelector("canvas")!.focus());
    expect(input).toHaveFocus();
    expect(fireEvent.keyDown(input, { key: "w", code: "KeyW" })).toBe(true);
    expect(sendEvent).not.toHaveBeenCalled();
    fireEvent.input(input, { target: { value: "w" }, inputType: "insertText" });
    expect(sendEvent).toHaveBeenCalledExactlyOnceWith({
      type: "type",
      text: "w",
    });
    expect(input.value).toBe("");
  });

  it.each(["before", "after"])(
    "sends only committed Chinese with the final input %s compositionend",
    async (order) => {
      const { input, sendEvent } = setup();
      fireEvent.compositionStart(input);
      expect(
        fireEvent.keyDown(input, { key: "n", keyCode: 229, isComposing: true }),
      ).toBe(true);
      fireEvent.input(input, { target: { value: "nihao" }, isComposing: true });
      expect(sendEvent).not.toHaveBeenCalled();
      await act(async () => {
        if (order === "before") {
          fireEvent.input(input, {
            target: { value: "你好" },
            isComposing: false,
          });
        } else {
          input.value = "你好";
        }
        fireEvent.compositionEnd(input, { data: "你好" });
        if (order === "after") {
          fireEvent.input(input, {
            target: { value: "你好" },
            isComposing: false,
          });
        }
      });
      expect(sendEvent).toHaveBeenCalledExactlyOnceWith({
        type: "type",
        text: "你好",
      });
      expect(input.value).toBe("");
    },
  );

  it("does not send Enter while it confirms an IME candidate", () => {
    const { input, sendEvent } = setup();
    fireEvent.compositionStart(input);
    expect(fireEvent.keyDown(input, { key: "Enter", isComposing: true })).toBe(
      true,
    );
    expect(sendEvent).not.toHaveBeenCalled();
  });

  it("forwards editing keys and modifier flags in order", () => {
    const { input, sendEvent } = setup();
    for (const key of ["Backspace", "Delete", "ArrowLeft", "Tab", "Enter"]) {
      expect(fireEvent.keyDown(input, { key, code: key, shiftKey: true })).toBe(
        false,
      );
    }
    fireEvent.keyDown(input, {
      key: "a",
      code: "KeyA",
      keyCode: 65,
      metaKey: true,
    });
    expect(sendEvent.mock.calls.map(([event]) => event.key)).toEqual([
      "Backspace",
      "Delete",
      "ArrowLeft",
      "Tab",
      "Enter",
      "a",
    ]);
    expect(sendEvent.mock.calls[0][0]).toMatchObject({ shiftKey: true });
    expect(sendEvent.mock.calls.at(-1)?.[0]).toMatchObject({
      type: "keydown",
      key: "a",
      code: "KeyA",
      keyCode: 65,
      metaKey: true,
    });
  });

  it("keeps paste native and sends its full Unicode text once", () => {
    const { input, sendEvent } = setup();
    expect(fireEvent.keyDown(input, { key: "v", metaKey: true })).toBe(true);
    fireEvent.input(input, {
      target: { value: "测试 browser\n🙂" },
      inputType: "insertFromPaste",
    });
    expect(sendEvent).toHaveBeenCalledExactlyOnceWith({
      type: "type",
      text: "测试 browser\n🙂",
    });
  });

  it("does not intercept address bar keys or read-only viewers", () => {
    const { input, sendEvent } = setup(false);
    fireEvent.keyDown(input, { key: "Backspace" });
    fireEvent.input(input, { target: { value: "a" } });
    fireEvent.keyDown(screen.getByLabelText("Address"), { key: "Backspace" });
    expect(sendEvent).not.toHaveBeenCalled();
  });
});
