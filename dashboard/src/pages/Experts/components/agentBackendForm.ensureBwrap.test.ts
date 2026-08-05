import { describe, expect, it } from "vitest";
import { ensureBwrapMessage, ensureBwrapToastKind } from "./agentBackendForm";

describe("ensureBwrap helpers", () => {
  it("maps status to toast kind", () => {
    expect(ensureBwrapToastKind("ready")).toBe("none");
    expect(ensureBwrapToastKind("installed")).toBe("success");
    expect(ensureBwrapToastKind("skipped")).toBe("warning");
    expect(ensureBwrapToastKind("degraded")).toBe("warning");
  });

  it("resolves i18n keys for toast text", () => {
    const t = (key: string, opts?: Record<string, unknown>) =>
      `${key}:${String(opts?.detail ?? "")}`;
    expect(
      ensureBwrapMessage({ status: "degraded", detail: "no sudo" }, t),
    ).toBe("experts.ensureBwrap.degraded:no sudo");
  });
});
