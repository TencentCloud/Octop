import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  recordTagClick,
  readTagClicks,
  TAG_FILTER_CLICKS_PREFIX,
} from "./tagFilterClicks";

const AGENT_A = "agt_a";
const AGENT_B = "agt_b";

describe("tagFilterClicks", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("returns an empty record when no clicks are stored", () => {
    expect(readTagClicks(AGENT_A)).toEqual({});
  });

  it("increments a tag's activation count", () => {
    recordTagClick(AGENT_A, "学习");
    recordTagClick(AGENT_A, "学习");
    recordTagClick(AGENT_A, "天气");

    expect(readTagClicks(AGENT_A)).toEqual({ 学习: 2, 天气: 1 });
  });

  it("keeps click counts isolated by agent", () => {
    recordTagClick(AGENT_A, "学习");
    recordTagClick(AGENT_B, "工作");

    expect(readTagClicks(AGENT_A)).toEqual({ 学习: 1 });
    expect(readTagClicks(AGENT_B)).toEqual({ 工作: 1 });
  });

  it("retains only the 50 highest-frequency tags", () => {
    for (let i = 0; i <= 50; i += 1) {
      recordTagClick(AGENT_A, `tag-${String(i).padStart(2, "0")}`);
    }

    const clicks = readTagClicks(AGENT_A);
    expect(Object.keys(clicks)).toHaveLength(50);
    expect(clicks["tag-00"]).toBe(1);
    expect(clicks["tag-50"]).toBeUndefined();
  });

  it("silently degrades for malformed data or unavailable storage", () => {
    localStorage.setItem(`${TAG_FILTER_CLICKS_PREFIX}${AGENT_A}`, "not-json");
    expect(readTagClicks(AGENT_A)).toEqual({});
    expect(() => recordTagClick(AGENT_A, "学习")).not.toThrow();

    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    expect(() => recordTagClick(AGENT_A, "天气")).not.toThrow();
  });
});
