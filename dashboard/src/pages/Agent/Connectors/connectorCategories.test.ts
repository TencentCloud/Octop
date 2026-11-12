import { describe, expect, it } from "vitest";

import {
  CONNECTOR_CATEGORY_ALL,
  connectorCategoryOptions,
  matchesConnectorCategory,
} from "./connectorCategories";

describe("connectorCategoryOptions", () => {
  const labelFor = (category: string) => category;

  it("puts All first and follows the catalog order", () => {
    const options = connectorCategoryOptions(
      ["travel", "office", "knowledge"],
      labelFor,
      "All",
    );
    expect(options.map((option) => option.value)).toEqual([
      CONNECTOR_CATEGORY_ALL,
      "office",
      "knowledge",
      "travel",
    ]);
    expect(options[0]?.label).toBe("All");
  });

  it("appends unknown categories after the known ones", () => {
    const options = connectorCategoryOptions(
      ["zeta", "office", "alpha"],
      labelFor,
      "All",
    );
    expect(options.map((option) => option.value)).toEqual([
      "",
      "office",
      "alpha",
      "zeta",
    ]);
  });

  it("returns no pills when the catalog has no categories", () => {
    expect(connectorCategoryOptions([], labelFor, "All")).toEqual([]);
  });
});

describe("matchesConnectorCategory", () => {
  it("keeps every item when All is selected", () => {
    expect(matchesConnectorCategory("office", "")).toBe(true);
    expect(matchesConnectorCategory(undefined, "")).toBe(true);
  });

  it("keeps only the selected category", () => {
    expect(matchesConnectorCategory("office", "office")).toBe(true);
    expect(matchesConnectorCategory("travel", "office")).toBe(false);
    expect(matchesConnectorCategory(undefined, "office")).toBe(false);
  });
});
