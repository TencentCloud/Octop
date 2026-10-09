export interface CanvasPoint {
  x: number;
  y: number;
}

/** Map a screen pointer position to canvas pixel coordinates. */
export function getCanvasCoords(
  canvas: HTMLCanvasElement | null,
  e: { clientX: number; clientY: number },
): CanvasPoint {
  if (!canvas) return { x: 0, y: 0 };
  const rect = canvas.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return { x: 0, y: 0 };
  // The canvas element is rendered with object-fit: contain — the bitmap is
  // scaled to fit while preserving aspect ratio and centered, leaving
  // letterbox whitespace on the sides (or top/bottom). The old mapping
  // (canvas.width / rect.width) ignored that whitespace, so pointer
  // coordinates drifted toward the right/bottom. Compute the actual drawn
  // area (drawW/drawH) and compensate for the centered offsets first, then
  // map by the uniform scale factor.
  const imgW = canvas.width;
  const imgH = canvas.height;
  // Bitmap may be 0 when no frame has been painted yet (or cleared by the
  // caller); mapping against a zero bitmap would produce Infinity/NaN and
  // round() to NaN, which JSON serializes as null -> pointer jumps to origin.
  if (imgW === 0 || imgH === 0) return { x: 0, y: 0 };
  const scale = Math.min(rect.width / imgW, rect.height / imgH);
  if (!Number.isFinite(scale) || scale <= 0) return { x: 0, y: 0 };
  const drawW = imgW * scale;
  const drawH = imgH * scale;
  const offsetX = rect.left + (rect.width - drawW) / 2;
  const offsetY = rect.top + (rect.height - drawH) / 2;
  return {
    x: Math.round((e.clientX - offsetX) / scale),
    y: Math.round((e.clientY - offsetY) / scale),
  };
}

/** Per-canvas coalescing state (WeakMap so a disposed viewer leaks nothing). */
type FramePaintState = {
  decoding: boolean;
  pending: string | null;
  dropped: number;
};

const paintStates = new WeakMap<HTMLCanvasElement, FramePaintState>();

function framePaintState(canvas: HTMLCanvasElement): FramePaintState {
  let state = paintStates.get(canvas);
  if (!state) {
    state = { decoding: false, pending: null, dropped: 0 };
    paintStates.set(canvas, state);
  }
  return state;
}

/**
 * Paint a JPEG base64 frame onto a canvas (WebSocket stream).
 *
 * Frames can arrive faster than the browser can decode + blit them (screencast over a
 * public link: 30fps x 50-200KB/frame). Starting one decode per arriving frame queues
 * work, so the picture lags further behind reality every second and the backlog keeps
 * growing after a hiccup. Therefore: at most one decode in flight per canvas, and the
 * waiting slot holds only the newest frame - a stale intermediate frame is dropped
 * rather than decoded, because nobody asks to see last second's screen twice.
 */
export function paintBase64JpegToCanvas(
  canvas: HTMLCanvasElement | null,
  base64Data: string,
): void {
  if (!canvas) return;
  const state = framePaintState(canvas);
  if (state.decoding) {
    if (state.pending !== null) state.dropped += 1;
    state.pending = base64Data;
    return;
  }
  state.decoding = true;
  const settle = () => {
    state.decoding = false;
    const next = state.pending;
    state.pending = null;
    if (next !== null) paintBase64JpegToCanvas(canvas, next);
  };
  const img = new Image();
  img.onload = () => {
    try {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      if (canvas.width !== img.width || canvas.height !== img.height) {
        canvas.width = img.width;
        canvas.height = img.height;
      }
      ctx.imageSmoothingEnabled = true;
      if ("imageSmoothingQuality" in ctx) {
        ctx.imageSmoothingQuality = "high";
      }
      ctx.drawImage(img, 0, 0);
    } finally {
      settle();
    }
  };
  // A corrupt/truncated frame must not wedge the pipeline: without this the canvas would
  // stay "decoding" forever and every later frame would pile into the pending slot.
  img.onerror = () => settle();
  img.src = `data:image/jpeg;base64,${base64Data}`;
}

/** How many waiting frames this canvas has dropped so far (diagnostics/tests). */
export function readFramePaintDrops(canvas: HTMLCanvasElement | null): number {
  return canvas ? framePaintState(canvas).dropped : 0;
}

/** Reset coalescing state (tests / reattaching a stream to an existing canvas). */
export function resetFramePaintState(canvas: HTMLCanvasElement | null): void {
  if (!canvas) return;
  paintStates.set(canvas, { decoding: false, pending: null, dropped: 0 });
}


/** Paint a screenshot blob onto a canvas (HTTP polling). */
export async function paintBlobToCanvas(
  canvas: HTMLCanvasElement | null,
  blob: Blob,
): Promise<boolean> {
  if (!canvas) return false;
  const bitmap = await createImageBitmap(blob);
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0);
  bitmap.close();
  return true;
}

export function clearCanvas(canvas: HTMLCanvasElement | null): void {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
}
