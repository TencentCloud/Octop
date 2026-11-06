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
  it("skips the catalog when the picker or the groups radio cannot appear", () => {
    expect(needsGroupCatalog({ userCount: 1, groupCount: 4 })).toBe(false);
    expect(needsGroupCatalog({ userCount: 3, groupCount: 0 })).toBe(false);
  });

  it("loads the catalog when groups can be chosen, or the counts are unknown", () => {
    expect(needsGroupCatalog({ userCount: 3, groupCount: 2 })).toBe(true);
    expect(needsGroupCatalog({ userCount: null, groupCount: null })).toBe(true);
  });
});

describe("showGroupVisibilityOption", () => {
  it("hides the group choice when there are no groups", () => {
    expect(showGroupVisibilityOption(ready(), "owner")).toBe(false);
    expect(showGroupVisibilityOption(ready(), "all")).toBe(false);
  });

  it("keeps the group choice when the resource is already limited to groups", () => {
    expect(showGroupVisibilityOption(ready(), "groups")).toBe(true);
  });

  it("shows the group choice when groups exist", () => {
    expect(showGroupVisibilityOption(ready({ groupCount: 2 }), "all")).toBe(
      true,
    );
  });

  it("falls back to the catalog when the count is unknown", () => {
    expect(
      showGroupVisibilityOption(
        ready({ groupCount: null, groupsLoaded: true, groupCountFromList: 0 }),
        "all",
      ),
    ).toBe(false);
    expect(
      showGroupVisibilityOption(
        ready({ groupCount: null, groupsLoaded: false, groupCountFromList: 0 }),
        "all",
      ),
    ).toBe(true);
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

  it("keeps owner and everyone when several accounts have no groups", () => {
    expect(
      isVisibilityControlVisible(ready(), {
        allowOwner: true,
        visibility: "owner",
      }),
    ).toBe(true);
  });

  it("hides an everyone-only picker when there are no groups", () => {
    expect(
      isVisibilityControlVisible(ready(), {
        allowOwner: false,
        visibility: "all",
      }),
    ).toBe(false);
  });

  it("keeps a groups-only picker that is already restricted", () => {
    expect(
      isVisibilityControlVisible(ready(), {
        allowOwner: false,
        visibility: "groups",
      }),
    ).toBe(true);
  });
});
