import { describe, expect, it } from "vitest";
import {
  isVisibilityControlVisible,
  needsGroupCatalog,
  showGroupVisibilityOption,
  type AudienceSnapshot,
} from "./visibilityChrome";

function ready(patch: Partial<AudienceSnapshot> = {}): AudienceSnapshot {
  return {
    status: "ready",
    userCount: 2,
    groupCount: 0,
    groupsLoaded: true,
    groupCountFromList: 0,
    ...patch,
  };
}

describe("needsGroupCatalog", () => {
  it("skips the catalog when the picker cannot appear or groups are empty", () => {
    expect(needsGroupCatalog({ userCount: 1, groupCount: 4 })).toBe(false);
    expect(needsGroupCatalog({ userCount: 3, groupCount: 0 })).toBe(false);
  });

  it("loads the catalog when groups can be chosen, or the counts are unknown", () => {
    expect(needsGroupCatalog({ userCount: 3, groupCount: 2 })).toBe(true);
    expect(needsGroupCatalog({ userCount: null, groupCount: null })).toBe(true);
  });
});

describe("showGroupVisibilityOption", () => {
  it("always shows the group choice once the picker is visible", () => {
    expect(showGroupVisibilityOption(ready(), "owner")).toBe(true);
    expect(showGroupVisibilityOption(ready(), "all")).toBe(true);
    expect(showGroupVisibilityOption(ready(), "groups")).toBe(true);
    expect(showGroupVisibilityOption(ready({ groupCount: 2 }), "all")).toBe(
      true,
    );
  });
});

describe("isVisibilityControlVisible", () => {
  it("stays hidden until the audience is known", () => {
    expect(
      isVisibilityControlVisible(
        { ...ready(), status: "loading" },
        { allowOwner: true, visibility: "owner" },
      ),
    ).toBe(false);
  });

  it("hides the picker when only one account can sign in", () => {
    expect(
      isVisibilityControlVisible(ready({ userCount: 1, groupCount: 3 }), {
        allowOwner: true,
        visibility: "owner",
      }),
    ).toBe(false);
  });

  it("keeps the picker when several accounts have no groups", () => {
    expect(
      isVisibilityControlVisible(ready(), {
        allowOwner: true,
        visibility: "owner",
      }),
    ).toBe(true);
    expect(
      isVisibilityControlVisible(ready(), {
        allowOwner: false,
        visibility: "all",
      }),
    ).toBe(true);
  });

  it("keeps a groups-restricted picker", () => {
    expect(
      isVisibilityControlVisible(ready(), {
        allowOwner: false,
        visibility: "groups",
      }),
    ).toBe(true);
  });
});
