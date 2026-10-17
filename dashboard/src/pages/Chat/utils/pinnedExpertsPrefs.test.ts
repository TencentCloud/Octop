import { afterEach, describe, expect, it } from "vitest";
import {
  PINNED_EXPERTS_STORAGE_KEY,
  pinnedExpertsStorageKey,
  readPinnedExpertIds,
  sortExpertsByPin,
  togglePinnedExpertId,
  writePinnedExpertIds,
} from "./pinnedExpertsPrefs";

describe("pinnedExpertsPrefs", () => {
  afterEach(() => {
    localStorage.removeItem(PINNED_EXPERTS_STORAGE_KEY);
    localStorage.removeItem(pinnedExpertsStorageKey(7));
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
});
