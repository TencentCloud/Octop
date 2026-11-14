import { afterEach, describe, expect, it } from "vitest";
import {
  EXPERT_SORT_STORAGE_KEY,
  PINNED_EXPERTS_STORAGE_KEY,
  expertSortStorageKey,
  pinnedExpertsStorageKey,
  readExpertSortMode,
  readPinnedExpertIds,
  sortExpertsByPin,
  togglePinnedExpertId,
  writeExpertSortMode,
  writePinnedExpertIds,
} from "./pinnedExpertsPrefs";

describe("pinnedExpertsPrefs", () => {
  afterEach(() => {
    localStorage.removeItem(PINNED_EXPERTS_STORAGE_KEY);
    localStorage.removeItem(pinnedExpertsStorageKey(7));
    localStorage.removeItem(EXPERT_SORT_STORAGE_KEY);
    localStorage.removeItem(expertSortStorageKey(7));
  });

  it("returns empty when unset", () => {
    expect(readPinnedExpertIds()).toEqual([]);
  });

  it("pins to the front and unpins on the second toggle", () => {
    expect(togglePinnedExpertId("a", 7)).toEqual(["a"]);
    expect(togglePinnedExpertId("b", 7)).toEqual(["b", "a"]);
    expect(togglePinnedExpertId("b", 7)).toEqual(["a"]);
    expect(readPinnedExpertIds()).toEqual([]);
  });

  it("ignores corrupt JSON", () => {
    localStorage.setItem(PINNED_EXPERTS_STORAGE_KEY, "{not-json");
    expect(readPinnedExpertIds()).toEqual([]);
  });

  it("clears key when empty", () => {
    writePinnedExpertIds(["x"], null);
    writePinnedExpertIds([], null);
    expect(localStorage.getItem(PINNED_EXPERTS_STORAGE_KEY)).toBeNull();
  });

  it("sorts pinned experts ahead of newer ones", () => {
    const agents = [
      { id: 3, agent_id: "c" },
      { id: 1, agent_id: "a" },
      { id: 2, agent_id: "b" },
    ];
    expect(sortExpertsByPin(agents, ["a", "b"]).map((a) => a.agent_id)).toEqual(
      ["a", "b", "c"],
    );
  });

  it("sorts recent chats ahead of never-chatted experts", () => {
    const agents = [
      { id: 1, agent_id: "old", last_active: 100 },
      { id: 3, agent_id: "fresh" },
      { id: 2, agent_id: "mid", last_active: 40 },
    ];
    expect(sortExpertsByPin(agents, []).map((a) => a.agent_id)).toEqual([
      "old",
      "mid",
      "fresh",
    ]);
    expect(
      sortExpertsByPin(agents, [], "newest").map((a) => a.agent_id),
    ).toEqual(["fresh", "mid", "old"]);
    expect(
      sortExpertsByPin(agents, [], "oldest").map((a) => a.agent_id),
    ).toEqual(["old", "mid", "fresh"]);
    expect(
      sortExpertsByPin(agents, ["fresh"], "recent").map((a) => a.agent_id),
    ).toEqual(["fresh", "old", "mid"]);
  });

  it("remembers the sort per user and ignores unknown values", () => {
    expect(readExpertSortMode(7)).toBe("recent");
    expect(writeExpertSortMode("oldest", 7)).toBe("oldest");
    expect(readExpertSortMode(7)).toBe("oldest");
    expect(readExpertSortMode()).toBe("recent");
    localStorage.setItem(expertSortStorageKey(7), "nope");
    expect(readExpertSortMode(7)).toBe("recent");
  });
});
