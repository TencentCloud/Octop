import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { createRef } from "react";
import { useBrowserCanvasInteraction } from "./useBrowserCanvasInteraction";

function fakeCoords(x: number, y: number) {
  return { clientX: x, clientY: y };
}

function dispatchPointer(
  target: HTMLElement,
  type: string,
  clientX: number,
  clientY: number,
) {
  const ev = new Event(type, { bubbles: true }) as Event & {
    clientX: number;
    clientY: number;
  };
  Object.defineProperty(ev, "clientX", { value: clientX });
  Object.defineProperty(ev, "clientY", { value: clientY });
  target.dispatchEvent(ev);
}

function setupCanvas() {
  const canvas = document.createElement("canvas");
  Object.defineProperty(canvas, "getBoundingClientRect", {
    value: () => ({
      left: 0,
      top: 0,
      width: 200,
      height: 100,
      right: 200,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }),
  });
  Object.defineProperty(canvas, "width", { value: 200 });
  Object.defineProperty(canvas, "height", { value: 100 });
  canvas.setPointerCapture = vi.fn();
  canvas.releasePointerCapture = vi.fn();
  canvas.hasPointerCapture = vi.fn(() => true);
  const canvasRef = createRef<HTMLCanvasElement | null>();
  // @ts-expect-error mutable ref for test
  canvasRef.current = canvas;
  return { canvas, canvasRef };
}

describe("useBrowserCanvasInteraction", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("delegates drag to the shared remote pointer protocol", () => {
    const onEvent = vi.fn();
    const { canvas, canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useBrowserCanvasInteraction({
        enabled: true,
        canvasRef,
        onEvent,
      }),
    );

    act(() => {
      result.current.onPointerDown({
        button: 0,
        pointerId: 1,
        preventDefault: vi.fn(),
        currentTarget: canvas,
        ...fakeCoords(10, 10),
      } as unknown as React.PointerEvent<HTMLElement>);
    });
    act(() => {
      dispatchPointer(canvas, "pointermove", 40, 50);
    });
    act(() => {
      dispatchPointer(canvas, "pointerup", 40, 50);
    });

    const types = onEvent.mock.calls.map((c) => c[0].type);
    expect(types[0]).toBe("mousedown");
    expect(types).toContain("mousemove");
    expect(types.at(-1)).toBe("mouseup");
  });
});
