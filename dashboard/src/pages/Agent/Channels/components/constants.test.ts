import { describe, expect, it } from "vitest";

import {
  DEFAULT_CHANNEL_DISPLAY_CONFIG,
  DEFAULT_QQ_GROUP_CONTEXT_CONFIG,
  normalizeQqGroupContextConfig,
} from "./constants";

describe("channel display defaults", () => {
  it("uses invoke delivery for external IM channels", () => {
    expect(DEFAULT_CHANNEL_DISPLAY_CONFIG.response_mode).toBe("invoke");
  });
});

describe("normalizeQqGroupContextConfig", () => {
  it("uses safe QQ group defaults for missing config", () => {
    expect(normalizeQqGroupContextConfig(undefined)).toEqual(
      DEFAULT_QQ_GROUP_CONTEXT_CONFIG,
    );
  });

  it("accepts JSON values left by older channel form drafts", () => {
    expect(
      normalizeQqGroupContextConfig(
        '{"enabled":true,"visibility":"mention_recent","history_limit":20}',
      ),
    ).toMatchObject({
      enabled: true,
      visibility: "mention_recent",
      activation: "mention",
      history: "recent",
      history_limit: 20,
    });
  });

  it("forces mention-only visibility to discard passive history", () => {
    expect(
      normalizeQqGroupContextConfig({
        visibility: "mention_only",
        activation: "always",
        history: "recent",
      }),
    ).toMatchObject({
      visibility: "mention_only",
      activation: "mention",
      history: "none",
    });
  });

  it("keeps active replies and per-group overrides with full visibility", () => {
    const groups = {
      "group-1": { activation: "mention", history_limit: 5 },
    };
    expect(
      normalizeQqGroupContextConfig({
        visibility: "all",
        activation: "always",
        history: "recent",
        history_limit: 25,
        groups,
      }),
    ).toMatchObject({
      visibility: "all",
      activation: "always",
      history_limit: 25,
      groups,
    });
  });
});
