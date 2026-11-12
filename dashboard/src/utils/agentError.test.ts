import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import {
  formatAgentError,
  isAgentChatReady,
  shortAgentError,
} from "./agentError";

const t = ((key: string) => key) as unknown as TFunction;

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

/**
 * An expert card shows its error in a single ellipsised line, so the full
 * sentence loses the part that matters. Model-config errors get a short form
 * because the card carries the "去配置模型" action itself.
 */
describe("shortAgentError", () => {
  it("shortens both model-config errors", () => {
    expect(shortAgentError("octop:agent_errors.no_models_configured", t)).toBe(
      "agent_errors.no_models_configured_short",
    );
    expect(shortAgentError("octop:agent_errors.model_ref_unavailable", t)).toBe(
      "agent_errors.model_ref_unavailable_short",
    );
  });

  it("shortens the raw backend wording too", () => {
    expect(
      shortAgentError("agent requires providers but none enabled", t),
    ).toBe("agent_errors.no_models_configured_short");
  });

  it("leaves every other error at full length", () => {
    const raw = "harness crashed on boot";
    expect(shortAgentError(raw, t)).toBe(formatAgentError(raw, t));
    expect(shortAgentError(null, t)).toBe("");
  });
});
