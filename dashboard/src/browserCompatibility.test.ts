import { readFileSync } from "node:fs";
import path from "node:path";
import { JSDOM } from "jsdom";

const indexHtml = readFileSync(path.resolve("index.html"), "utf8");

describe("dashboard browser compatibility bootstrap", () => {
  it("polyfills Object.hasOwn before module scripts run", () => {
    const dom = new JSDOM(indexHtml, {
      runScripts: "dangerously",
      url: "http://localhost/",
      beforeParse(window) {
        Reflect.deleteProperty(window.Object, "hasOwn");
      },
    });

    const objectCtor = dom.window.Object as typeof Object;
    const prototype = { inherited: true };
    const value = Object.assign(Object.create(prototype), { own: true });

    expect(objectCtor.hasOwn(value, "own")).toBe(true);
    expect(objectCtor.hasOwn(value, "inherited")).toBe(false);
    expect(Object.keys(objectCtor)).not.toContain("hasOwn");
  });

  it("keeps an existing Object.hasOwn implementation", () => {
    const nativeHasOwn = vi.fn(() => true);
    const dom = new JSDOM(indexHtml, {
      runScripts: "dangerously",
      url: "http://localhost/",
      beforeParse(window) {
        Object.defineProperty(window.Object, "hasOwn", {
          value: nativeHasOwn,
          configurable: true,
          writable: true,
        });
      },
    });

    expect(dom.window.Object.hasOwn).toBe(nativeHasOwn);
  });

  it("polyfills structuredClone when the browser has none", () => {
    const dom = new JSDOM(indexHtml, {
      runScripts: "dangerously",
      url: "http://localhost/",
      beforeParse(window) {
        Object.defineProperty(window, "structuredClone", {
          value: undefined,
          configurable: true,
          writable: true,
        });
      },
    });

    const clone = dom.window.structuredClone as <T>(value: T) => T;
    const source = { label: "edge", points: [{ x: 1, y: 2 }] };
    const result = clone(source);

    expect(result).toEqual(source);
    expect(result.points[0]).not.toBe(source.points[0]);
    expect(clone(undefined)).toBeUndefined();
  });

  it("keeps an existing structuredClone implementation", () => {
    const nativeClone = vi.fn((value: unknown) => value);
    const dom = new JSDOM(indexHtml, {
      runScripts: "dangerously",
      url: "http://localhost/",
      beforeParse(window) {
        Object.defineProperty(window, "structuredClone", {
          value: nativeClone,
          configurable: true,
          writable: true,
        });
      },
    });

    expect(dom.window.structuredClone).toBe(nativeClone);
  });

  it("polyfills Array.prototype.at for legacy browsers", () => {
    const dom = new JSDOM(indexHtml, {
      runScripts: "dangerously",
      url: "http://localhost/",
      beforeParse(window) {
        Object.defineProperty(window.Array.prototype, "at", {
          value: undefined,
          configurable: true,
          writable: true,
        });
      },
    });

    expect(dom.window.eval("[1, 2, 3].at(-1)")).toBe(3);
    expect(dom.window.eval("[1, 2, 3].at(0)")).toBe(1);
    expect(dom.window.eval("[1, 2, 3].at(9)")).toBeUndefined();
    expect(dom.window.Object.keys(dom.window.Array.prototype)).not.toContain(
      "at",
    );
  });

  it("keeps an existing Array.prototype.at implementation", () => {
    const nativeAt = vi.fn(() => "native");
    const dom = new JSDOM(indexHtml, {
      runScripts: "dangerously",
      url: "http://localhost/",
      beforeParse(window) {
        Object.defineProperty(window.Array.prototype, "at", {
          value: nativeAt,
          configurable: true,
          writable: true,
        });
      },
    });

    expect(dom.window.Array.prototype.at).toBe(nativeAt);
  });
});
