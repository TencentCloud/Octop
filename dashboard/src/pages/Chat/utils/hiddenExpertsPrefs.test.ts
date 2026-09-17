import { afterEach, describe, expect, it } from "vitest";
import {
  HIDDEN_SHARED_EXPERTS_STORAGE_KEY,
  hideExpertId,
  hiddenExpertsStorageKey,
  readHiddenExpertIds,
  unhideExpertId,
  writeHiddenExpertIds,
} from "./hiddenExpertsPrefs";

describe("hiddenExpertsPrefs", () => {
  afterEach(() => {
    localStorage.removeItem(HIDDEN_SHARED_EXPERTS_STORAGE_KEY);
    localStorage.removeItem(hiddenExpertsStorageKey(7));
  });

  it("returns empty when unset", () => {
    expect([...readHiddenExpertIds()]).toEqual([]);
  });

  it("round-trips hide and unhide per user", () => {
    hideExpertId("a", 7);
    hideExpertId("b", 7);
    expect([...readHiddenExpertIds(7)].sort()).toEqual(["a", "b"]);
    unhideExpertId("a", 7);
    expect([...readHiddenExpertIds(7)]).toEqual(["b"]);
    expect([...readHiddenExpertIds()]).toEqual([]);
  });

  it("ignores corrupt JSON", () => {
    localStorage.setItem(HIDDEN_SHARED_EXPERTS_STORAGE_KEY, "{not-json");
    expect([...readHiddenExpertIds()]).toEqual([]);
  });

  it("clears key when empty", () => {
    writeHiddenExpertIds(["x"], null);
    writeHiddenExpertIds([], null);
    expect(localStorage.getItem(HIDDEN_SHARED_EXPERTS_STORAGE_KEY)).toBeNull();
  });
});
