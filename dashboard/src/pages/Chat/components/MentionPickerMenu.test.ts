import { describe, expect, it } from "vitest";
import { buildMentionItems, firstFileMentionIndex } from "./MentionPickerMenu";

describe("buildMentionItems", () => {
  it("includes installed subagents as @slug picks", () => {
    const items = buildMentionItems(
      "",
      [],
      [],
      [
        {
          slug: "researcher",
          name: "研究员",
          path: "agents/researcher.md",
          emoji: "🔎",
        },
      ],
    );
    expect(items).toEqual([
      { kind: "subagent", slug: "researcher", label: "研究员" },
    ]);
  });

  it("does not preload leftover files on an empty query", () => {
    const items = buildMentionItems(
      "",
      [],
      [],
      [],
      [{ path: "docs/api.md", label: "api.md" }],
    );
    expect(items).toEqual([]);
  });

  it("appends workspace files after people unless the query looks like a path", () => {
    const connector = {
      mcp_server_name: "notes",
      label: "Notes for api.md",
      kind: "http",
    };
    const file = { path: "docs/api.md", label: "api.md" };
    expect(
      buildMentionItems("api", [connector], [], [], [file]).map(
        (item) => item.kind,
      ),
    ).toEqual(["connector", "file"]);
    expect(
      buildMentionItems("api.md", [connector], [], [], [file], {
        filesFirst: true,
      }).map((item) => item.kind),
    ).toEqual(["file", "connector"]);
    expect(
      firstFileMentionIndex(
        buildMentionItems("api.md", [connector], [], [], [file], {
          filesFirst: true,
        }),
      ),
    ).toBe(0);
  });
});
