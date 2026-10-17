import { describe, expect, it } from "vitest";
import {
  expertVisibleInNavSearch,
  filterSessionNames,
} from "./navSessionSearch";

describe("navSessionSearch", () => {
  it("keeps every expert when the query is blank", () => {
    expect(expertVisibleInNavSearch("Ada", ["notes"], "  ")).toBe(true);
  });

  it("matches an expert name or a conversation title", () => {
    expect(expertVisibleInNavSearch("Ada", ["weekly"], "ada")).toBe(true);
    expect(expertVisibleInNavSearch("Ada", ["weekly plan"], "plan")).toBe(true);
    expect(expertVisibleInNavSearch("Ada", ["weekly"], "bob")).toBe(false);
  });

  it("filters conversation titles", () => {
    expect(filterSessionNames(["Weekly", "Standup"], "week")).toEqual([
      "Weekly",
    ]);
    expect(filterSessionNames(["Weekly"], "")).toEqual(["Weekly"]);
  });
});
