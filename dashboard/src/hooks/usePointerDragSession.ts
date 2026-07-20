/**
 * Shared pointer-drag session: document listeners + rAF-batched moves.
 *
 * Call from a pointerdown handler after capturing start geometry. Prefer DOM
 * writes in ``onMove``; commit React state in ``onEnd``.
 */

export interface PointerDragSessionOptions {
  pointerId: number;
  target: HTMLElement;
  cursor?: string;
  onMove: (clientX: number, clientY: number) => void;
  onEnd?: () => void;
}

/** Start a drag session; returns a disposer (normally unused — ends on pointerup). */
export function beginPointerDragSession(
  options: PointerDragSessionOptions,
): () => void {
  const { pointerId, target, cursor, onMove, onEnd } = options;

  try {
    target.setPointerCapture(pointerId);
  } catch {
    /* ignore */
  }

  if (cursor) document.body.style.cursor = cursor;
  document.body.style.userSelect = "none";

  let pending: { x: number; y: number } | null = null;
  let frame: number | null = null;

  const flush = () => {
    frame = null;
    if (!pending) return;
    onMove(pending.x, pending.y);
  };

  const onPointerMove = (ev: Event) => {
    const pev = ev as PointerEvent;
    pending = { x: pev.clientX, y: pev.clientY };
    if (frame !== null) return;
    frame = requestAnimationFrame(flush);
  };

  const cleanup = () => {
    if (frame !== null) {
      cancelAnimationFrame(frame);
      frame = null;
    }
    if (pending) {
      onMove(pending.x, pending.y);
      pending = null;
    }
    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", onPointerUp);
    document.removeEventListener("pointercancel", onPointerUp);
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
    onEnd?.();
  };

  const onPointerUp = () => {
    cleanup();
  };

  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", onPointerUp);
  document.addEventListener("pointercancel", onPointerUp);

  return cleanup;
}
