import { describe, expect, it } from "vitest";
import { resolveSessionWorkStatus } from "./sessionWorkStatus";

describe("resolveSessionWorkStatus", () => {
  it("marks a live or server-active turn as working", () => {
    expect(resolveSessionWorkStatus({ id: "thr_1" }, new Set(["thr_1"]))).toBe(
      "working",
    );
    expect(
      resolveSessionWorkStatus({ id: "thr_1", turnActive: true }, new Set()),
    ).toBe("working");
  });

  it("prefers working over waiting", () => {
    expect(
      resolveSessionWorkStatus(
        { id: "thr_1", turnActive: true, awaitingUser: true },
        new Set(),
      ),
    ).toBe("working");
  });

  it("marks a HITL pause as waiting", () => {
    expect(
      resolveSessionWorkStatus({ id: "thr_1", awaitingUser: true }, new Set()),
    ).toBe("waiting");
  });

  it("treats an idle finished thread as idle (no completed badge)", () => {
    expect(resolveSessionWorkStatus({ id: "thr_1" }, new Set())).toBe("idle");
  });
});
