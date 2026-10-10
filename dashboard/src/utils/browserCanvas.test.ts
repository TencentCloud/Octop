// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { getCanvasCoords } from "./browserCanvas";

type RectInput = { left: number; top: number; width: number; height: number };

function makeCanvas(
  bitmapWidth: number,
  bitmapHeight: number,
  rect: RectInput,
): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  Object.defineProperty(canvas, "width", { value: bitmapWidth });
  Object.defineProperty(canvas, "height", { value: bitmapHeight });
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

describe("getCanvasCoords (object-fit: contain mapping)", () => {
  it("maps 1:1 when the element and bitmap aspect ratios match", () => {
    // 200x100 element, 200x100 bitmap → contain fills the element exactly.
    const canvas = makeCanvas(200, 100, { left: 0, top: 0, width: 200, height: 100 });
    expect(getCanvasCoords(canvas, { clientX: 50, clientY: 25 })).toEqual({
      x: 50,
      y: 25,
    });
    expect(getCanvasCoords(canvas, { clientX: 200, clientY: 100 })).toEqual({
      x: 200,
      y: 100,
    });
  });

  it("accounts for horizontal letterboxing (wide element, tall bitmap)", () => {
    // Element 1000x500 (2:1), bitmap 800x600 (4:3) → the image is shown at
    // 666.67x500 centered, with (1000-666.67)/2 ≈ 166.67px bars left/right.
    const canvas = makeCanvas(800, 600, { left: 0, top: 0, width: 1000, height: 500 });
    // Click on the left black bar → clamped to the image's left edge.
    expect(getCanvasCoords(canvas, { clientX: 100, clientY: 250 })).toEqual({
      x: 0,
      y: 300,
    });
    // Click on the image's top-left corner.
    expect(getCanvasCoords(canvas, { clientX: 166.67, clientY: 0 })).toEqual({
      x: 0,
      y: 0,
    });
    // Click on the image's center → maps to the bitmap center.
    expect(getCanvasCoords(canvas, { clientX: 500, clientY: 250 })).toEqual({
      x: 400,
      y: 300,
    });
    // Click on the right black bar → clamped to the image's right edge.
    expect(getCanvasCoords(canvas, { clientX: 950, clientY: 250 })).toEqual({
      x: 800,
      y: 300,
    });
  });

  it("accounts for vertical letterboxing (tall element, wide bitmap)", () => {
    // Element 400x800 (1:2), bitmap 800x400 (2:1) → the image is shown at
    // 400x200 centered vertically.
    const canvas = makeCanvas(800, 400, { left: 0, top: 0, width: 400, height: 800 });
    expect(getCanvasCoords(canvas, { clientX: 200, clientY: 300 })).toEqual({
      x: 400,
      y: 0,
    });
    expect(getCanvasCoords(canvas, { clientX: 200, clientY: 500 })).toEqual({
      x: 400,
      y: 400,
    });
    // Below the image (bottom black bar) → clamped.
    expect(getCanvasCoords(canvas, { clientX: 200, clientY: 700 })).toEqual({
      x: 400,
      y: 400,
    });
  });

  it("respects the element's page offset", () => {
    const canvas = makeCanvas(200, 100, { left: 100, top: 50, width: 200, height: 100 });
    expect(getCanvasCoords(canvas, { clientX: 150, clientY: 75 })).toEqual({
      x: 50,
      y: 25,
    });
  });

  it("returns zeros for degenerate rects and empty bitmaps", () => {
    const zeroRect = makeCanvas(200, 100, { left: 0, top: 0, width: 0, height: 100 });
    expect(getCanvasCoords(zeroRect, { clientX: 5, clientY: 5 })).toEqual({
      x: 0,
      y: 0,
    });
    const emptyBitmap = makeCanvas(0, 0, { left: 0, top: 0, width: 200, height: 100 });
    expect(getCanvasCoords(emptyBitmap, { clientX: 5, clientY: 5 })).toEqual({
      x: 0,
      y: 0,
    });
    expect(getCanvasCoords(null, { clientX: 5, clientY: 5 })).toEqual({
      x: 0,
      y: 0,
    });
  });
});
