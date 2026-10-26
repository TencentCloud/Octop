import { useCallback, useMemo, useRef, useState } from "react";
import type { ChangeEvent, CompositionEvent } from "react";

export interface ImeSearchInputProps {
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onCompositionStart: (event: CompositionEvent<HTMLInputElement>) => void;
  onCompositionEnd: (event: CompositionEvent<HTMLInputElement>) => void;
}

/**
 * IME-safe search-input state for search-as-you-type UIs.
 *
 * ``value`` always follows the input — including IME composition
 * intermediates — so the controlled element never fights the input method
 * (freezing it mid-composition makes React reset the DOM value and breaks
 * Chinese / Japanese / Korean typing). Consumers should react to
 * ``committed``: it tracks ``value`` on plain typing, holds still while a
 * composition is active, and lands on the final text at ``compositionend``.
 *
 * antd Input (rc-input) suppresses the post-composition onChange, so the
 * commit must read the input inside ``onCompositionEnd``.
 */
export function useImeSearchInput(initial = "") {
  const [value, setValueState] = useState(initial);
  const [committed, setCommitted] = useState(initial);
  const composingRef = useRef(false);

  const onCompositionStart = useCallback(() => {
    composingRef.current = true;
  }, []);

  const onCompositionEnd = useCallback(
    (event: CompositionEvent<HTMLInputElement>) => {
      composingRef.current = false;
      const final = event.currentTarget.value;
      setValueState(final);
      setCommitted(final);
    },
    [],
  );

  const onChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.value;
    setValueState(next);
    if (!composingRef.current) setCommitted(next);
  }, []);

  const setValue = useCallback((next: string) => {
    setValueState(next);
    setCommitted(next);
  }, []);

  const inputProps: ImeSearchInputProps = useMemo(
    () => ({ value, onChange, onCompositionStart, onCompositionEnd }),
    [value, onChange, onCompositionStart, onCompositionEnd],
  );

  return { value, committed, setValue, inputProps };
}
