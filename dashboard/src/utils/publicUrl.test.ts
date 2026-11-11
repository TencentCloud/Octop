import { describe, expect, it } from "vitest";
import { publicUrl, routerBasename } from "./publicUrl";

describe("publicUrl", () => {
  it("prefixes the Vite base path", () => {
    expect(publicUrl("sw.js")).toMatch(/sw\.js$/);
    expect(publicUrl("/logo.png")).toMatch(/logo\.png$/);
  });
});

describe("routerBasename", () => {
  it("is undefined at domain root", () => {
    // Vitest default BASE_URL is "/".
    expect(routerBasename()).toBeUndefined();
  });
});
