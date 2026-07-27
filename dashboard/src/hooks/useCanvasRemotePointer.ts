import {
  useCallback,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  type WheelEvent as ReactWheelEvent,
} from "react";
import { getCanvasCoords } from "../utils/browserCanvas";

const DRAG_THRESHOLD = 4;
const MOVE_INTERVAL_MS = 33;
const DBLCLICK_MS = 400;
const DBLCLICK_DISTANCE = 6;

const BUTTON_MASK: Record<string, number> = {
  left: 1,
  right: 2,
  middle: 4,
  none: 0,
};

export interface CanvasRemotePointerOptions {
  enabled: boolean;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  onEvent: (event: Record<string, unknown>) => void;
  /** Merge extra fields (e.g. desktop screen/canvas size). */
  enrichPayload?: (coords: { x: number; y: number }) => Record<string, unknown>;
}

function buttonName(button: number): "left" | "middle" | "right" {
  if (button === 1) return "middle";
  if (button === 2) return "right";
  return "left";
}

/**
 * Shared remote canvas pointer protocol for browser + desktop streams.
 *
 * - pointerdown → immediate mousedown
 * - move while pressed → throttled mousemove (buttons pressed)
 * - pointerup → flush latest move, then mouseup (CDP/OS synthesizes click)
 * - hover move → mousemove with buttons 0
 * - contextmenu → right mousedown + mouseup
 * - wheel → scroll
 */
export function useCanvasRemotePointer({
  enabled,
  canvasRef,
  onEvent,
  enrichPayload,
}: CanvasRemotePointerOptions) {
  const pressingRef = useRef(false);
  const movedRef = useRef(false);
  const anchorRef = useRef({ x: 0, y: 0 });
  const buttonRef = useRef<"left" | "middle" | "right">("left");
  const lastMoveSentRef = useRef(0);
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null);
  const clickCountRef = useRef(1);
  const lastClickRef = useRef<{
    x: number;
    y: number;
    button: string;
    at: number;
  } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const getCoords = useCallback(
    (e: { clientX: number; clientY: number }) =>
      getCanvasCoords(canvasRef.current, e),
    [canvasRef],
  );

  const emit = useCallback(
    (
      type: string,
      coords: { x: number; y: number },
      extra: Record<string, unknown> = {},
    ) => {
      onEvent({
        type,
        x: coords.x,
        y: coords.y,
        ...(enrichPayload?.(coords) ?? {}),
        ...extra,
      });
    },
    [onEvent, enrichPayload],
  );

  const flushPendingMove = useCallback(
    (buttons: number, button: string) => {
      const pending = pendingMoveRef.current;
      if (!pending) return;
      pendingMoveRef.current = null;
      lastMoveSentRef.current = Date.now();
      emit("mousemove", pending, { button, buttons });
    },
    [emit],
  );

  const queuePressedMove = useCallback(
    (coords: { x: number; y: number }) => {
      pendingMoveRef.current = coords;
      const now = Date.now();
      if (now - lastMoveSentRef.current < MOVE_INTERVAL_MS) return;
      flushPendingMove(BUTTON_MASK[buttonRef.current], buttonRef.current);
    },
    [flushPendingMove],
  );

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      if (!enabled || e.button === 2) return;
      e.preventDefault();
      const target = e.currentTarget;
      target.setPointerCapture(e.pointerId);
      canvasRef.current?.focus();
      const coords = getCoords(e);
      pressingRef.current = true;
      movedRef.current = false;
      pendingMoveRef.current = null;
      anchorRef.current = coords;
      buttonRef.current = buttonName(e.button);
      const button = buttonRef.current;
      const buttons = BUTTON_MASK[button];
      const prev = lastClickRef.current;
      const now = Date.now();
      if (
        prev &&
        prev.button === button &&
        now - prev.at <= DBLCLICK_MS &&
        Math.abs(prev.x - coords.x) <= DBLCLICK_DISTANCE &&
        Math.abs(prev.y - coords.y) <= DBLCLICK_DISTANCE
      ) {
        clickCountRef.current = Math.min(3, clickCountRef.current + 1);
      } else {
        clickCountRef.current = 1;
      }
      lastClickRef.current = {
        x: coords.x,
        y: coords.y,
        button,
        at: now,
      };
      const clickCount = clickCountRef.current;
      setIsDragging(false);
      emit("mousedown", coords, { button, buttons, clickCount });

      const onMove = (ev: PointerEvent) => {
        if (!pressingRef.current) return;
        const cur = getCoords(ev);
        if (
          !movedRef.current &&
          (Math.abs(cur.x - anchorRef.current.x) > DRAG_THRESHOLD ||
            Math.abs(cur.y - anchorRef.current.y) > DRAG_THRESHOLD)
        ) {
          movedRef.current = true;
          setIsDragging(true);
        }
        queuePressedMove(cur);
      };

      const onUp = (ev: PointerEvent) => {
        if (!pressingRef.current) return;
        pressingRef.current = false;
        setIsDragging(false);
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

        // Flush the latest drag coordinate even if it was still inside the
        // throttle window — but skip for a pure click (no movement).
        if (movedRef.current) {
          pendingMoveRef.current = cur;
          flushPendingMove(BUTTON_MASK[buttonRef.current], buttonRef.current);
        } else {
          pendingMoveRef.current = null;
        }
        emit("mouseup", cur, {
          button: buttonRef.current,
          buttons: 0,
          clickCount: clickCountRef.current,
        });
      };

      target.addEventListener("pointermove", onMove);
      target.addEventListener("pointerup", onUp);
      target.addEventListener("pointercancel", onUp);
    },
    [enabled, canvasRef, getCoords, emit, queuePressedMove, flushPendingMove],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      if (!enabled || pressingRef.current) return;
      // Ignore hover while any mouse button is held (drag uses capture listeners).
      if (e.buttons !== 0) return;
      const coords = getCoords(e);
      const now = Date.now();
      if (now - lastMoveSentRef.current < MOVE_INTERVAL_MS) {
        pendingMoveRef.current = coords;
        return;
      }
      pendingMoveRef.current = null;
      lastMoveSentRef.current = now;
      emit("mousemove", coords, { button: "none", buttons: 0 });
    },
    [enabled, getCoords, emit],
  );

  const onPointerLeave = useCallback(() => {
    if (!enabled || pressingRef.current) return;
    // Flush throttled hover so the remote cursor does not lag at the edge.
    flushPendingMove(0, "none");
  }, [enabled, flushPendingMove]);

  const onContextMenu = useCallback(
    (e: ReactMouseEvent<HTMLElement>) => {
      if (!enabled) return;
      e.preventDefault();
      const coords = getCoords(e);
      emit("mousedown", coords, { button: "right", buttons: 2 });
      emit("mouseup", coords, { button: "right", buttons: 0 });
    },
    [enabled, getCoords, emit],
  );

  const onDoubleClick = useCallback((e: ReactMouseEvent<HTMLElement>) => {
    // clickCount on press/release drives CDP dblclick; suppress browser menu.
    e.preventDefault();
  }, []);

  const onWheel = useCallback(
    (e: ReactWheelEvent) => {
      if (!enabled) return;
      e.preventDefault();
      const coords = getCoords(e);
      emit("scroll", coords, {
        deltaX: e.deltaX,
        deltaY: e.deltaY,
        delta_x: e.deltaX,
        delta_y: e.deltaY,
      });
    },
    [enabled, getCoords, emit],
  );

  return {
    getCoords,
    onPointerDown,
    onPointerMove,
    onPointerLeave,
    onContextMenu,
    onDoubleClick,
    onWheel,
    handleWheel: onWheel,
    isDragging,
    pointerStyle: { touchAction: "none" as const },
  };
}
