import {
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  type WheelEvent as ReactWheelEvent,
} from "react";
import { getCanvasCoords } from "../utils/browserCanvas";

interface DesktopCanvasInteractionOptions {
  enabled: boolean;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  screenWidth: number;
  screenHeight: number;
  onEvent: (event: Record<string, unknown>) => void;
}

const DRAG_THRESHOLD = 4;
/** Defer single-click so native dblclick can cancel it (matches OS double-click timing). */
const CLICK_DELAY_MS = 300;
const MOVE_INTERVAL_MS = 33;

export function useDesktopCanvasInteraction({
  enabled,
  canvasRef,
  screenWidth,
  screenHeight,
  onEvent,
}: DesktopCanvasInteractionOptions) {
  const draggingRef = useRef(false);
  const movedRef = useRef(false);
  const anchorRef = useRef({ x: 0, y: 0 });
  const buttonRef = useRef("left");
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastMoveSentRef = useRef(0);

  const basePayload = useCallback(
    (coords: { x: number; y: number }) => ({
      x: coords.x,
      y: coords.y,
      canvas_width: canvasRef.current?.width ?? 0,
      canvas_height: canvasRef.current?.height ?? 0,
      screen_width: screenWidth,
      screen_height: screenHeight,
    }),
    [canvasRef, screenWidth, screenHeight],
  );

  const getCoords = useCallback(
    (e: { clientX: number; clientY: number }) =>
      getCanvasCoords(canvasRef.current, e),
    [canvasRef],
  );

  const clearClickTimer = useCallback(() => {
    if (clickTimerRef.current !== null) {
      clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => clearClickTimer(), [clearClickTimer]);

  const onWheel = useCallback(
    (e: ReactWheelEvent) => {
      if (!enabled) return;
      e.preventDefault();
      const coords = getCoords(e);
      onEvent({
        type: "scroll",
        ...basePayload(coords),
        delta_x: e.deltaX,
        delta_y: e.deltaY,
      });
    },
    [enabled, getCoords, onEvent, basePayload],
  );

  const onContextMenu = useCallback(
    (e: ReactMouseEvent<HTMLCanvasElement>) => {
      if (!enabled) return;
      e.preventDefault();
      clearClickTimer();
      const coords = getCoords(e);
      onEvent({ type: "click", ...basePayload(coords), button: "right" });
    },
    [enabled, getCoords, onEvent, basePayload, clearClickTimer],
  );

  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent) => {
      if (!enabled) return;
      e.preventDefault();
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        onEvent({ type: "type", text: e.key });
      } else {
        onEvent({ type: "keydown", key: e.key });
      }
    },
    [enabled, onEvent],
  );

  const onKeyUp = useCallback(
    (e: ReactKeyboardEvent) => {
      if (!enabled) return;
      e.preventDefault();
      onEvent({ type: "keyup", key: e.key });
    },
    [enabled, onEvent],
  );

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLCanvasElement>) => {
      if (!enabled || e.button === 2) return;
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      canvasRef.current?.focus();
      const coords = getCoords(e);
      draggingRef.current = true;
      movedRef.current = false;
      anchorRef.current = coords;
      buttonRef.current = e.button === 1 ? "middle" : "left";
      const target = e.currentTarget;

      const onMove = (ev: PointerEvent) => {
        if (!draggingRef.current) return;
        const cur = getCoords(ev);
        if (
          !movedRef.current &&
          (Math.abs(cur.x - anchorRef.current.x) > DRAG_THRESHOLD ||
            Math.abs(cur.y - anchorRef.current.y) > DRAG_THRESHOLD)
        ) {
          movedRef.current = true;
          clearClickTimer();
          onEvent({
            type: "mousedown",
            ...basePayload(anchorRef.current),
            button: buttonRef.current,
          });
        }
        if (movedRef.current) {
          const now = Date.now();
          if (now - lastMoveSentRef.current < MOVE_INTERVAL_MS) return;
          lastMoveSentRef.current = now;
          onEvent({
            type: "mousemove",
            ...basePayload(cur),
            button: buttonRef.current,
          });
        }
      };

      const onUp = (ev: PointerEvent) => {
        if (!draggingRef.current) return;
        draggingRef.current = false;
        const cur = getCoords(ev);
        try {
          if (target.hasPointerCapture(e.pointerId)) {
            target.releasePointerCapture(e.pointerId);
          }
        } catch {
          // ignore
        }
        target.removeEventListener("pointermove", onMove);
        target.removeEventListener("pointerup", onUp);
        target.removeEventListener("pointercancel", onUp);

        if (movedRef.current) {
          onEvent({
            type: "mouseup",
            ...basePayload(cur),
            button: buttonRef.current,
          });
          return;
        }

        clearClickTimer();
        clickTimerRef.current = setTimeout(() => {
          clickTimerRef.current = null;
          onEvent({
            type: "click",
            ...basePayload(cur),
            button: buttonRef.current,
          });
        }, CLICK_DELAY_MS);
      };

      target.addEventListener("pointermove", onMove);
      target.addEventListener("pointerup", onUp);
      target.addEventListener("pointercancel", onUp);
    },
    [enabled, canvasRef, getCoords, onEvent, basePayload, clearClickTimer],
  );

  const onDoubleClick = useCallback(
    (e: ReactMouseEvent<HTMLCanvasElement>) => {
      if (!enabled) return;
      e.preventDefault();
      clearClickTimer();
      const coords = getCoords(e);
      onEvent({ type: "dblclick", ...basePayload(coords), button: "left" });
    },
    [enabled, getCoords, onEvent, basePayload, clearClickTimer],
  );

  return {
    onPointerDown,
    onDoubleClick,
    onContextMenu,
    onWheel,
    onKeyDown,
    onKeyUp,
    canvasProps: {
      tabIndex: 0 as const,
      style: { touchAction: "none" as const },
    },
  };
}
