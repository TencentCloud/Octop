import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { createRef } from "react";
import { useCanvasRemotePointer } from "./useCanvasRemotePointer";

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

describe("useCanvasRemotePointer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("emits mousedown immediately on pointerdown", () => {
    const onEvent = vi.fn();
    const { canvas, canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useCanvasRemotePointer({ enabled: true, canvasRef, onEvent }),
    );

    act(() => {
      result.current.onPointerDown({
        button: 0,
        pointerId: 1,
        preventDefault: vi.fn(),
        currentTarget: canvas,
        ...fakeCoords(12, 18),
      } as unknown as React.PointerEvent<HTMLElement>);
    });

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "mousedown",
        clickCount: 1,
      }),
    );
  });

  it("increments clickCount on rapid second press", () => {
    const onEvent = vi.fn();
    const { canvas, canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useCanvasRemotePointer({ enabled: true, canvasRef, onEvent }),
    );

    const down = (x: number, y: number) => {
      result.current.onPointerDown({
        button: 0,
        pointerId: 1,
        preventDefault: vi.fn(),
        currentTarget: canvas,
        ...fakeCoords(x, y),
      } as unknown as React.PointerEvent<HTMLElement>);
    };

    act(() => {
      down(12, 18);
    });
    act(() => {
      dispatchPointer(canvas, "pointerup", 12, 18);
    });
    act(() => {
      down(13, 19);
    });

    const downs = onEvent.mock.calls.filter((c) => c[0].type === "mousedown");
    expect(downs[0]?.[0]).toMatchObject({ clickCount: 1 });
    expect(downs[1]?.[0]).toMatchObject({ clickCount: 2 });
  });

  it("flushes the latest mousemove before mouseup even inside the throttle window", () => {
    const onEvent = vi.fn();
    const { canvas, canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useCanvasRemotePointer({ enabled: true, canvasRef, onEvent }),
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
    // Second move inside 33ms throttle — must still be flushed on up.
    act(() => {
      dispatchPointer(canvas, "pointermove", 55, 66);
    });
    act(() => {
      dispatchPointer(canvas, "pointerup", 55, 66);
    });

    const types = onEvent.mock.calls.map((c) => c[0].type as string);
    expect(types[0]).toBe("mousedown");
    expect(types).toContain("mousemove");
    expect(types.at(-1)).toBe("mouseup");
    const lastMove = [...onEvent.mock.calls]
      .reverse()
      .find((c) => c[0].type === "mousemove");
    expect(lastMove?.[0]).toMatchObject({ x: 55, y: 66, buttons: 1 });
    expect(onEvent.mock.calls.at(-1)?.[0]).toMatchObject({
      type: "mouseup",
      x: 55,
      y: 66,
      buttons: 0,
    });
  });

  it("emits hover mousemove with buttons 0 when not pressing", () => {
    const onEvent = vi.fn();
    const { canvas, canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useCanvasRemotePointer({ enabled: true, canvasRef, onEvent }),
    );

    act(() => {
      result.current.onPointerMove({
        buttons: 0,
        preventDefault: vi.fn(),
        currentTarget: canvas,
        ...fakeCoords(33, 44),
      } as unknown as React.PointerEvent<HTMLElement>);
    });

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "mousemove",
        x: 33,
        y: 44,
        button: "none",
        buttons: 0,
      }),
    );
  });

  it("flushes pending hover move on pointer leave", () => {
    const onEvent = vi.fn();
    const { canvas, canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useCanvasRemotePointer({ enabled: true, canvasRef, onEvent }),
    );

    act(() => {
      result.current.onPointerMove({
        buttons: 0,
        preventDefault: vi.fn(),
        currentTarget: canvas,
        ...fakeCoords(10, 10),
      } as unknown as React.PointerEvent<HTMLElement>);
    });
    onEvent.mockClear();
    act(() => {
      result.current.onPointerMove({
        buttons: 0,
        preventDefault: vi.fn(),
        currentTarget: canvas,
        ...fakeCoords(40, 50),
      } as unknown as React.PointerEvent<HTMLElement>);
    });
    expect(onEvent).not.toHaveBeenCalled();
    act(() => {
      result.current.onPointerLeave();
    });
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "mousemove",
        x: 40,
        y: 50,
        buttons: 0,
      }),
    );
  });

  it("emits right-button press/release on contextmenu", () => {
    const onEvent = vi.fn();
    const { canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useCanvasRemotePointer({ enabled: true, canvasRef, onEvent }),
    );

    act(() => {
      result.current.onContextMenu({
        preventDefault: vi.fn(),
        ...fakeCoords(8, 9),
      } as unknown as React.MouseEvent<HTMLElement>);
    });

    expect(onEvent.mock.calls.map((c) => c[0].type)).toEqual([
      "mousedown",
      "mouseup",
    ]);
    expect(onEvent.mock.calls[0][0]).toMatchObject({
      button: "right",
      buttons: 2,
      x: 8,
      y: 9,
    });
    expect(onEvent.mock.calls[1][0]).toMatchObject({
      button: "right",
      buttons: 0,
      x: 8,
      y: 9,
    });
  });

  it("does not emit a separate click after a simple press/release", () => {
    const onEvent = vi.fn();
    const { canvas, canvasRef } = setupCanvas();
    const { result } = renderHook(() =>
      useCanvasRemotePointer({ enabled: true, canvasRef, onEvent }),
    );

    act(() => {
      result.current.onPointerDown({
        button: 0,
        pointerId: 1,
        preventDefault: vi.fn(),
        currentTarget: canvas,
        ...fakeCoords(20, 20),
      } as unknown as React.PointerEvent<HTMLElement>);
    });
    act(() => {
      dispatchPointer(canvas, "pointerup", 21, 21);
    });
    act(() => {
      vi.advanceTimersByTime(400);
    });

    const types = onEvent.mock.calls.map((c) => c[0].type);
    expect(types).toEqual(["mousedown", "mouseup"]);
  });
});
