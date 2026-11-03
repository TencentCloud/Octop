import { afterEach, describe, expect, it, vi } from "vitest";
import { getCanvasCoords } from "./browserCanvas";

function canvasWithRect(
  width: number,
  height: number,
  rect: { left: number; top: number; width: number; height: number },
): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  Object.defineProperty(canvas, "width", { value: width });
  Object.defineProperty(canvas, "height", { value: height });
  Object.defineProperty(canvas, "getBoundingClientRect", {
    value: () => ({
      ...rect,
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("accounts for object-fit contain letterboxing", () => {
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      objectFit: "contain",
    } as CSSStyleDeclaration);
    const canvas = canvasWithRect(1280, 800, {
      left: 100,
      top: 50,
      width: 560,
      height: 690,
    });

    expect(getCanvasCoords(canvas, { clientX: 380, clientY: 395 })).toEqual({
      x: 640,
      y: 400,
    });
  });

  it("keeps stretch mapping for canvases without object-fit contain", () => {
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      objectFit: "fill",
    } as CSSStyleDeclaration);
    const canvas = canvasWithRect(200, 100, {
      left: 20,
      top: 10,
      width: 100,
      height: 100,
    });

    expect(getCanvasCoords(canvas, { clientX: 70, clientY: 60 })).toEqual({
      x: 100,
      y: 50,
    });
  });
});
