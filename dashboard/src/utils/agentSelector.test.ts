import { describe, expect, it } from "vitest";
import {
  labelSelectorGroups,
  nextPickerSelection,
  showSelectorGroupLabels,
  splitBarOverflow,
  type BarChipSize,
} from "./agentSelector";

describe("labelSelectorGroups", () => {
  it("labels local and remote groups", () => {
    const groups = labelSelectorGroups(
      [
        { agent_id: "local-1" },
        {
          agent_id: "bridge:c1:a1",
          bridge: true,
          bridge_connection_id: "c1",
          bridge_connection_name: "云端",
        },
      ],
      "专家",
      (name) => `${name}·专家`,
    );
    expect(groups.map((group) => group.label)).toEqual(["专家", "云端·专家"]);
  });
});

describe("showSelectorGroupLabels", () => {
  it("hides labels when only local experts exist", () => {
    expect(showSelectorGroupLabels([{ key: "local" }], 0)).toBe(false);
  });

  it("shows labels when teams or remotes exist", () => {
    expect(showSelectorGroupLabels([{ key: "local" }], 1)).toBe(true);
    expect(showSelectorGroupLabels([{ key: "local" }, { key: "c1" }], 0)).toBe(
      true,
    );
  });
});

describe("splitBarOverflow", () => {
  const chip = (
    id: string,
    groupKey: string,
    width = 80,
    groupLabelWidth = 0,
  ): BarChipSize => ({ id, width, groupKey, groupLabelWidth });

  it("keeps every chip when they fit", () => {
    expect(
      splitBarOverflow(
        [chip("a", "e"), chip("b", "e"), chip("c", "t")],
        "a",
        400,
        40,
      ),
    ).toEqual({ hiddenIds: [] });
  });

  it("hides chips that do not fit and keeps the selection", () => {
    const chips = [
      chip("a", "e", 100),
      chip("b", "e", 100),
      chip("c", "e", 100),
      chip("d", "e", 100),
    ];
    // 4×100 + 3×6 = 418; budget 260 - 40 - 6 = 214 → two chips (206)
    expect(splitBarOverflow(chips, "d", 260, 40).hiddenIds).toEqual(["b", "c"]);
    expect(splitBarOverflow(chips, "a", 260, 40).hiddenIds).toEqual(["c", "d"]);
  });
});

describe("nextPickerSelection", () => {
  const writer = { agent_id: "writer", is_owner: true };
  const crew = { agent_id: "crew", is_owner: true };

  it("keeps an owned team that the current page hides", () => {
    expect(
      nextPickerSelection("crew", [writer, crew], [writer]),
    ).toBeUndefined();
  });

  it("fills an empty selection from the visible list", () => {
    expect(nextPickerSelection(null, [writer, crew], [writer])).toBe("writer");
  });

  it("replaces a missing or share-only selection", () => {
    expect(nextPickerSelection("gone", [writer], [writer])).toBe("writer");
    expect(
      nextPickerSelection(
        "shared",
        [{ agent_id: "shared", is_shared: true, is_owner: false }, writer],
        [writer],
      ),
    ).toBe("writer");
  });
});
