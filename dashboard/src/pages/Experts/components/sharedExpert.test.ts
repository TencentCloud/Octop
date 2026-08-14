import { describe, expect, it } from "vitest";
import {
  isOwnedExpert,
  isSharedExpertViewer,
  ownedExperts,
} from "../../../utils/sharedExpert";

describe("isSharedExpertViewer", () => {
  it("identifies a shared expert viewed by someone other than its owner", () => {
    expect(isSharedExpertViewer({ is_shared: true, is_owner: false })).toBe(
      true,
    );
  });

  it("does not treat the owner or a private expert as a viewer", () => {
    expect(isSharedExpertViewer({ is_shared: true, is_owner: true })).toBe(
      false,
    );
    expect(isSharedExpertViewer({ is_shared: false, is_owner: false })).toBe(
      false,
    );
  });
});

describe("ownedExperts", () => {
  it("keeps owned experts and drops shared viewers for manage pages", () => {
    const agents = [
      { agent_id: "own", is_shared: true, is_owner: true },
      { agent_id: "shared", is_shared: true, is_owner: false },
      { agent_id: "private", is_shared: false, is_owner: true },
    ];
    expect(ownedExperts(agents).map((a) => a.agent_id)).toEqual([
      "own",
      "private",
    ]);
    expect(isOwnedExpert(agents[1]!)).toBe(false);
    expect(isOwnedExpert(agents[0]!)).toBe(true);
  });
});
