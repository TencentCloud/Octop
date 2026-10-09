import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getCanvasCoords,
  paintBase64JpegToCanvas,
  readFramePaintDrops,
  resetFramePaintState,
} from "./browserCanvas";

function fakeCanvas(
  pixelW: number,
  pixelH: number,
  rect: { left: number; top: number; width: number; height: number },
) {
  const canvas = document.createElement("canvas");
  Object.defineProperty(canvas, "width", { value: pixelW });
  Object.defineProperty(canvas, "height", { value: pixelH });
  Object.defineProperty(canvas, "getBoundingClientRect", {
    value: () => ({
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      x: rect.left,
      y: rect.top,
      toJSON: () => ({}),
    }),
  });
  return canvas;
}

describe("getCanvasCoords", () => {
  it("maps 1:1 when the canvas fills its box (no letterbox)", () => {
    const canvas = fakeCanvas(200, 100, { left: 0, top: 0, width: 200, height: 100 });
    expect(getCanvasCoords(canvas, { clientX: 55, clientY: 66 })).toEqual({
      x: 55,
      y: 66,
    });
  });

  it("compensates horizontal letterbox from object-fit: contain", () => {
    // 200x100 bitmap shown in a 250x100 box: scale=1, 25px whitespace each side.
    const canvas = fakeCanvas(200, 100, { left: 0, top: 0, width: 250, height: 100 });
    // Point at the bitmap center (x=125 is the visual center of the bitmap).
    expect(getCanvasCoords(canvas, { clientX: 125, clientY: 50 })).toEqual({
      x: 100,
      y: 50,
    });
    // Left edge of the drawn area maps to x=0 (not -25).
    expect(getCanvasCoords(canvas, { clientX: 25, clientY: 50 })).toEqual({
      x: 0,
      y: 50,
    });
  });

  it("compensates vertical letterbox from object-fit: contain", () => {
    // 200x100 bitmap shown in a 200x200 box: scale=1, 50px whitespace top/bottom.
    const canvas = fakeCanvas(200, 100, { left: 0, top: 0, width: 200, height: 200 });
    expect(getCanvasCoords(canvas, { clientX: 100, clientY: 100 })).toEqual({
      x: 100,
      y: 50,
    });
  });

  it("handles scaled-down bitmaps (scale < 1)", () => {
    // 400x200 bitmap shown in a 200x100 box: scale=0.5, no letterbox.
    const canvas = fakeCanvas(400, 200, { left: 0, top: 0, width: 200, height: 100 });
    expect(getCanvasCoords(canvas, { clientX: 100, clientY: 50 })).toEqual({
      x: 200,
      y: 100,
    });
  });

  it("respects non-zero box offset with letterbox", () => {
    const canvas = fakeCanvas(200, 100, { left: 40, top: 20, width: 250, height: 100 });
    // Bitmap center: box x = 40 + 125 = 165, y = 20 + 50 = 70.
    expect(getCanvasCoords(canvas, { clientX: 165, clientY: 70 })).toEqual({
      x: 100,
      y: 50,
    });
  });

  it("returns origin for null canvas / zero-sized box", () => {
    expect(getCanvasCoords(null, { clientX: 10, clientY: 10 })).toEqual({ x: 0, y: 0 });
    const canvas = fakeCanvas(200, 100, { left: 0, top: 0, width: 0, height: 0 });
    expect(getCanvasCoords(canvas, { clientX: 10, clientY: 10 })).toEqual({ x: 0, y: 0 });
  });

  it("returns origin when the bitmap is unpainted (0-sized)", () => {
    // canvas.width/height === 0 happens before the first frame is painted
    // (or when the caller clears it); mapping must not produce NaN.
    const canvas = fakeCanvas(0, 0, { left: 0, top: 0, width: 200, height: 100 });
    expect(getCanvasCoords(canvas, { clientX: 10, clientY: 10 })).toEqual({ x: 0, y: 0 });
  });

  it("returns origin when only one bitmap dimension is zero", () => {
    const canvas = fakeCanvas(200, 0, { left: 0, top: 0, width: 200, height: 100 });
    expect(getCanvasCoords(canvas, { clientX: 10, clientY: 10 })).toEqual({ x: 0, y: 0 });
    const canvas2 = fakeCanvas(0, 100, { left: 0, top: 0, width: 200, height: 100 });
    expect(getCanvasCoords(canvas2, { clientX: 10, clientY: 10 })).toEqual({ x: 0, y: 0 });
  });
});

/** Controllable Image stand-in: we decide when a frame finishes decoding. */
class FakeImage {
  static instances: FakeImage[] = [];
  src = "";
  width = 8;
  height = 8;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor() {
    FakeImage.instances.push(this);
  }

  succeed(): void {
    this.onload?.();
  }

  fail(): void {
    this.onerror?.();
  }
}

let canvas: HTMLCanvasElement;

beforeEach(() => {
  FakeImage.instances = [];
  vi.stubGlobal("Image", FakeImage as unknown as typeof Image);
  canvas = document.createElement("canvas");
  // jsdom has no 2d context; painting is not what these tests assert on.
  vi.spyOn(canvas, "getContext").mockReturnValue(null as never);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("paintBase64JpegToCanvas frame coalescing", () => {
  it("keeps at most one decode in flight per canvas", () => {
    paintBase64JpegToCanvas(canvas, "AAA");
    paintBase64JpegToCanvas(canvas, "BBB");

    expect(FakeImage.instances).toHaveLength(1);
    expect(FakeImage.instances[0].src).toContain("AAA");
  });

  it("draws the newest waiting frame once the running decode settles", () => {
    paintBase64JpegToCanvas(canvas, "AAA");
    paintBase64JpegToCanvas(canvas, "BBB");
    FakeImage.instances[0].succeed();

    expect(FakeImage.instances).toHaveLength(2);
    expect(FakeImage.instances[1].src).toContain("BBB");
    expect(readFramePaintDrops(canvas)).toBe(0); // BBB waited, nothing was thrown away
  });

  it("drops the stale intermediate frame instead of decoding it", () => {
    paintBase64JpegToCanvas(canvas, "AAA");
    paintBase64JpegToCanvas(canvas, "BBB");
    paintBase64JpegToCanvas(canvas, "CCC"); // BBB is now pointless: CCC is newer

    FakeImage.instances[0].succeed();
    expect(FakeImage.instances).toHaveLength(2);
    expect(FakeImage.instances[1].src).toContain("CCC");
    expect(readFramePaintDrops(canvas)).toBe(1);
  });

  it("a failing frame must not wedge the canvas forever", () => {
    paintBase64JpegToCanvas(canvas, "BAD");
    paintBase64JpegToCanvas(canvas, "GOOD");
    FakeImage.instances[0].fail(); // corrupt/truncated frame

    expect(FakeImage.instances).toHaveLength(2);
    expect(FakeImage.instances[1].src).toContain("GOOD");

    paintBase64JpegToCanvas(canvas, "NEXT");
    FakeImage.instances[1].succeed();
    expect(FakeImage.instances).toHaveLength(3);
    expect(FakeImage.instances[2].src).toContain("NEXT");
  });

  it("resetFramePaintState clears counters and the in-flight flag", () => {
    paintBase64JpegToCanvas(canvas, "AAA");
    paintBase64JpegToCanvas(canvas, "BBB");
    paintBase64JpegToCanvas(canvas, "CCC");
    expect(readFramePaintDrops(canvas)).toBe(1);

    resetFramePaintState(canvas);
    expect(readFramePaintDrops(canvas)).toBe(0);

    paintBase64JpegToCanvas(canvas, "DDD");
    // state was reset, so DDD starts a decode straight away instead of queueing behind AAA
    expect(FakeImage.instances).toHaveLength(2);
    expect(FakeImage.instances[1].src).toContain("DDD");
  });

  it("ignores a null canvas without throwing", () => {
    expect(() => paintBase64JpegToCanvas(null, "AAA")).not.toThrow();
    expect(readFramePaintDrops(null)).toBe(0);
    expect(() => resetFramePaintState(null)).not.toThrow();
  });
});
