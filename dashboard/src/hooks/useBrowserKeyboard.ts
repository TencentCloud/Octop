import {
  useCallback,
  useRef,
  type CompositionEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";

/** Keep a real text control focused so the local IME can compose before sending. */
export function useBrowserKeyboard(
  enabled: boolean,
  sendEvent: (event: Record<string, unknown>) => boolean,
) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);

  const flushText = useCallback(
    (input: HTMLTextAreaElement) => {
      if (!enabled || composing.current || !input.value) return;
      sendEvent({ type: "type", text: input.value });
      input.value = "";
    },
    [enabled, sendEvent],
  );

  const focusInput = useCallback(() => {
    if (enabled) inputRef.current?.focus({ preventScroll: true });
  }, [enabled]);

  const onInput = useCallback(
    (event: FormEvent<HTMLTextAreaElement>) => {
      if (!(event.nativeEvent as InputEvent).isComposing) {
        flushText(event.currentTarget);
      }
    },
    [flushText],
  );

  const onCompositionStart = useCallback(() => {
    composing.current = true;
  }, []);

  const onCompositionEnd = useCallback(
    (event: CompositionEvent<HTMLTextAreaElement>) => {
      composing.current = false;
      const input = event.currentTarget;
      // Browsers differ in whether the final input precedes compositionend.
      // Flush after both events; clearing the control prevents duplicate text.
      queueMicrotask(() => {
        if (inputRef.current === input) flushText(input);
      });
    },
    [flushText],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (!enabled) return;
      event.stopPropagation();
      if (
        composing.current ||
        event.nativeEvent.isComposing ||
        event.keyCode === 229 ||
        event.key === "Process" ||
        event.key === "Dead"
      ) {
        return;
      }
      // Text, dead keys and paste must reach the local input control. Its
      // input event forwards the committed text, including Unicode and paste.
      if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") {
        return;
      }
      if (["Shift", "Control", "Alt", "Meta", "AltGraph"].includes(event.key)) {
        return;
      }
      event.preventDefault();
      flushText(event.currentTarget);
      sendEvent({
        type: "keydown",
        key: event.key,
        code: event.code,
        keyCode: event.keyCode,
        altKey: event.altKey,
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey,
        shiftKey: event.shiftKey,
        repeat: event.repeat,
      });
    },
    [enabled, flushText, sendEvent],
  );

  return {
    inputRef,
    focusInput,
    onInput,
    onKeyDown,
    onCompositionStart,
    onCompositionEnd,
  };
}
