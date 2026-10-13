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
});
