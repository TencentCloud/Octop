import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChangeEvent, CompositionEvent } from "react";

import { useImeSearchInput } from "./useImeSearchInput";

function changeEvent(value: string): ChangeEvent<HTMLInputElement> {
  return { target: { value } } as unknown as ChangeEvent<HTMLInputElement>;
}

function compositionEvent(value: string): CompositionEvent<HTMLInputElement> {
  return {
    currentTarget: { value },
  } as unknown as CompositionEvent<HTMLInputElement>;
}

function typeViaChange(
  result: {
    current: ReturnType<typeof useImeSearchInput>;
  },
  value: string,
) {
  act(() => {
    result.current.inputProps.onChange(changeEvent(value));
  });
}

describe("useImeSearchInput", () => {
  it("updates value and committed on plain change events", () => {
    const { result } = renderHook(() => useImeSearchInput());
    typeViaChange(result, "hello");
    expect(result.current.value).toBe("hello");
    expect(result.current.committed).toBe("hello");
  });

  it("keeps value following the input while composing", () => {
    const { result } = renderHook(() => useImeSearchInput());
    act(() => {
      result.current.inputProps.onCompositionStart(compositionEvent("z"));
    });
    typeViaChange(result, "zhong");
    // Controlled value must track the DOM so the IME is not interrupted…
    expect(result.current.value).toBe("zhong");
    // …while the search trigger holds still on composition intermediates.
    expect(result.current.committed).toBe("");
  });

  it("commits the final text on composition end", () => {
    const { result } = renderHook(() => useImeSearchInput());
    act(() => {
      result.current.inputProps.onCompositionStart(compositionEvent("z"));
    });
    typeViaChange(result, "zhong wen");
    act(() => {
      result.current.inputProps.onCompositionEnd(compositionEvent("zhong wen"));
    });
    expect(result.current.value).toBe("zhong wen");
    expect(result.current.committed).toBe("zhong wen");
    typeViaChange(result, "zhong wen ");
    expect(result.current.value).toBe("zhong wen ");
    expect(result.current.committed).toBe("zhong wen ");
  });

  it("resets composing mode after composition end", () => {
    const { result } = renderHook(() => useImeSearchInput());
    act(() => {
      result.current.inputProps.onCompositionStart(compositionEvent("a"));
    });
    act(() => {
      result.current.inputProps.onCompositionEnd(compositionEvent("a"));
    });
    typeViaChange(result, "abc");
    expect(result.current.value).toBe("abc");
    expect(result.current.committed).toBe("abc");
  });

  it("setValue updates both value and committed programmatically", () => {
    const { result } = renderHook(() => useImeSearchInput());
    act(() => {
      result.current.inputProps.onCompositionStart(compositionEvent("z"));
    });
    act(() => {
      result.current.setValue("");
    });
    expect(result.current.value).toBe("");
    expect(result.current.committed).toBe("");
  });

  it("accepts an initial value", () => {
    const { result } = renderHook(() => useImeSearchInput("preset"));
    expect(result.current.value).toBe("preset");
    expect(result.current.committed).toBe("preset");
  });
});
