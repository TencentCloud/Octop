import { afterEach, describe, expect, it, vi } from "vitest";
import { applicationPathname, publicUrl, routerBasename } from "./publicUrl";

afterEach(() => vi.unstubAllEnvs());

describe("publicUrl", () => {
  it("prefixes the Vite base path", () => {
    expect(publicUrl("sw.js")).toMatch(/sw\.js$/);
    expect(publicUrl("/logo.png")).toMatch(/logo\.png$/);
  });
});

describe("applicationPathname", () => {
  it.each([
    ["/", "/login", "/login"],
    ["/octop/", "/octop/login", "/login"],
    [
      "/tools/octop/",
      "/tools/octop/login/oidc-complete",
      "/login/oidc-complete",
    ],
    ["/octop/", "/octop", "/"],
    ["/octop/", "/octopus/login", "/octopus/login"],
  ])(
    "strips only the complete public base %s from %s",
    (base, pathname, expected) => {
      vi.stubEnv("BASE_URL", base);
      expect(applicationPathname(pathname)).toBe(expected);
    },
  );
});

describe("routerBasename", () => {
  it("is undefined at domain root", () => {
    // Vitest default BASE_URL is "/".
    expect(routerBasename()).toBeUndefined();
  });
});
