import { describe, expect, it } from "vitest";
import {
  resolveTurnModelOverride,
  resolveTurnModelRef,
  userTurnsFromEnd,
} from "./chatMessages";

describe("resolveTurnModelRef", () => {
  it("sends only an explicit composer selection", () => {
    expect(resolveTurnModelRef("p/picked", null)).toBe("p/picked");
  });

  it("omits model when composer is Auto so backend can resolve expert default", () => {
    expect(resolveTurnModelRef(null, null)).toBeNull();
    expect(resolveTurnModelRef("", null)).toBeNull();
  });
});

describe("userTurnsFromEnd", () => {
  it("counts user turns from the selected message through the latest", () => {
    const messages = [
      { id: "u1", role: "user" },
      { id: "a1", role: "assistant" },
      { id: "u2", role: "user" },
      { id: "a2", role: "assistant" },
      { id: "u3", role: "user" },
    ];
    expect(userTurnsFromEnd(messages, "u2")).toBe(2);
    expect(userTurnsFromEnd(messages, "u3")).toBe(1);
    expect(userTurnsFromEnd(messages, "u1")).toBe(3);
    expect(userTurnsFromEnd(messages, "missing")).toBe(0);
  });
});
