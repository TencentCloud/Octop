import { describe, expect, it } from "vitest";
import { getCanvasCoords } from "./browserCanvas";

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
});
