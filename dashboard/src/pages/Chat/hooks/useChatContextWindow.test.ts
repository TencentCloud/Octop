import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import type { ResolvedModel } from "../../../api/types";
import {
  activeModelToRef,
  contextUsedPercent,
  useChatContextWindow,
} from "./useChatContextWindow";

const models: ResolvedModel[] = [
  {
    provider_id: 1,
    provider_name: "Tencent Cloud HAI",
    provider_kind: "openai",
    model: "MiniMax-M2.7",
    name: "MiniMax",
    context_window: 1_000_000,
  },
  {
    provider_id: 1,
    provider_name: "Tencent Cloud HAI",
    provider_kind: "openai",
    model: "Kimi-K2.5",
    name: "Kimi",
    context_window: 131_072,
  },
];

describe("useChatContextWindow", () => {
  it("uses selected model context window", () => {
    const { result } = renderHook(() =>
      useChatContextWindow(
        [],
        null,
        "Tencent Cloud HAI/Kimi-K2.5",
        models,
        null,
        "Tencent Cloud HAI/MiniMax-M2.7",
      ),
    );
    expect(result.current.contextMaxTokens).toBe(131_072);
  });

  it("falls back to global active model when composer is Auto", () => {
    const { result } = renderHook(() =>
      useChatContextWindow(
        [],
        null,
        null,
        models,
        null,
        "Tencent Cloud HAI/MiniMax-M2.7",
      ),
    );
    expect(result.current.contextMaxTokens).toBe(1_000_000);
  });

  it("does not default Auto to 128k when catalog has windows", () => {
    const { result } = renderHook(() =>
      useChatContextWindow([], null, null, models, null, null),
    );
    expect(result.current.contextMaxTokens).toBe(1_000_000);
  });

  it("uses last history input_tokens when stream usage is empty", () => {
    const { result } = renderHook(() =>
      useChatContextWindow(
        [
          {
            id: "a1",
            role: "assistant",
            content: "ok",
            status: "done",
            timestamp: 1,
            usage: { input_tokens: 4200, output_tokens: 9 },
          },
        ],
        null,
        null,
        models,
        null,
        null,
      ),
    );
    expect(result.current.contextUsedTokens).toBe(4200);
  });
});

describe("contextUsedPercent", () => {
  it("does not round a real occupancy to 0% against a 1M window", () => {
    expect(contextUsedPercent(4_200, 1_000_000)).toBe(1);
  });

  it("returns 0 when unused", () => {
    expect(contextUsedPercent(0, 128_000)).toBe(0);
  });
});

describe("activeModelToRef", () => {
  it("builds provider/model ref", () => {
    expect(activeModelToRef({ provider_name: "Hai", model: "m1" })).toBe(
      "Hai/m1",
    );
  });
});
