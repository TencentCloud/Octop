import { describe, expect, it } from "vitest";
import { isAgentChatReady } from "./agentError";

describe("isAgentChatReady", () => {
  it("treats a live remote expert as ready only while the peer is running", () => {
    expect(
      isAgentChatReady("running", { bridge: true, bridge_disconnected: false }),
    ).toBe(true);
    expect(
      isAgentChatReady("stopped", { bridge: true, bridge_disconnected: false }),
    ).toBe(false);
  });

  it("does not treat a dropped remote link as ready", () => {
    expect(
      isAgentChatReady("running", { bridge: true, bridge_disconnected: true }),
    ).toBe(false);
  });

  it("keeps the local running check", () => {
    expect(isAgentChatReady("running")).toBe(true);
    expect(isAgentChatReady("stopped")).toBe(false);
  });
});
