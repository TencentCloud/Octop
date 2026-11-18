import { describe, expect, it } from "vitest";
import { isLoopbackShareHost, publicShareAvailable } from "./publicShareHost";

describe("public share host", () => {
  it("hides sharing on loopback names", () => {
    for (const host of [
      "localhost",
      "LOCALHOST",
      "app.localhost",
      "127.0.0.1",
      "127.1.2.3",
      "::1",
      "[::1]",
      "0.0.0.0",
    ]) {
      expect(isLoopbackShareHost(host)).toBe(true);
      expect(publicShareAvailable(host)).toBe(false);
    }
  });

  it("keeps sharing on addresses other machines can open", () => {
    for (const host of ["192.168.1.8", "10.0.0.4", "octop.example.com"]) {
      expect(isLoopbackShareHost(host)).toBe(false);
      expect(publicShareAvailable(host)).toBe(true);
    }
  });
});
