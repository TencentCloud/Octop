import { describe, expect, it } from "vitest";
import { isPlaceholderToolName, preferToolName } from "./toolDisplayNames";

describe("preferToolName", () => {
  it("keeps the original name when a later update has no title", () => {
    expect(preferToolName("unknown", "Web Search")).toBe("Web Search");
    expect(preferToolName("  ", "Web Search")).toBe("Web Search");
  });

  it("uses a real incoming name", () => {
    expect(preferToolName("Web Search", "unknown")).toBe("Web Search");
  });

  it("keeps write_file when a later ACP title reuses the call", () => {
    expect(
      preferToolName(
        "Write /home/wally/GWN3MS/random_7f3a9c.txt",
        "write_file",
      ),
    ).toBe("write_file");
    expect(preferToolName("edit_file", "Write notes.md")).toBe("edit_file");
  });

  it("treats only a blank or unknown name as a placeholder", () => {
    expect(isPlaceholderToolName("unknown")).toBe(true);
    expect(isPlaceholderToolName("Web Search")).toBe(false);
  });
});
