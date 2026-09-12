import { describe, expect, it } from "vitest";
import { accountDisplayName, accountInitials } from "./accountDisplayName";

describe("accountDisplayName", () => {
  it("prefers display_name over username, matching the account avatar", () => {
    expect(accountDisplayName({ display_name: "Ada", username: "ada.l" })).toBe(
      "Ada",
    );
    expect(
      accountDisplayName({ display_name: "  Ada  ", username: "ada.l" }),
    ).toBe("Ada");
  });

  it("falls back to username when display_name is empty", () => {
    expect(accountDisplayName({ display_name: null, username: "ada.l" })).toBe(
      "ada.l",
    );
    expect(accountDisplayName({ display_name: "  ", username: "ada.l" })).toBe(
      "ada.l",
    );
  });

  it("returns empty when both are missing", () => {
    expect(accountDisplayName(null)).toBe("");
    expect(accountDisplayName({ display_name: null, username: null })).toBe("");
  });
});

describe("accountInitials", () => {
  it("uses the first character, matching the account avatar", () => {
    expect(accountInitials("Ada")).toBe("A");
    expect(accountInitials("李雷")).toBe("李");
    expect(accountInitials("")).toBe("?");
  });
});
