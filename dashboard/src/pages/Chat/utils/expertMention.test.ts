import { describe, expect, it } from "vitest";
import {
  ensureExpertMentions,
  expertMentionToken,
  mentionedExpertIds,
  mentionedSubagentSlugs,
  replaceMentionQuery,
  textHasExpertMention,
  toggleExpertMention,
} from "./expertMention";

describe("expertMentionToken", () => {
  it("prefixes the name and collapses whitespace", () => {
    expect(expertMentionToken("数据分析师")).toBe("@数据分析师");
    expect(expertMentionToken(" data analyst ")).toBe("@data-analyst");
  });
});

describe("toggleExpertMention", () => {
  it("inserts @Name into an empty composer with a trailing space", () => {
    expect(toggleExpertMention("", "分析师")).toEqual({
      text: "@分析师 ",
      cursor: 5,
    });
  });

  it("appends @Name after existing text", () => {
    expect(toggleExpertMention("帮我看看", "分析师").text).toBe(
      "帮我看看 @分析师 ",
    );
  });

  it("removes an existing mention", () => {
    expect(toggleExpertMention("@分析师 帮我看看", "分析师").text).toBe(
      "帮我看看",
    );
    expect(toggleExpertMention("请 @分析师 帮我", "分析师").text).toBe(
      "请 帮我",
    );
  });

  it("does not treat a longer name as the shorter one", () => {
    expect(textHasExpertMention("@分析师 看一下", "分析")).toBe(false);
    expect(textHasExpertMention("@分析师 看一下", "分析师")).toBe(true);
  });
});

describe("replaceMentionQuery", () => {
  it("replaces the typed @query with @Name", () => {
    expect(replaceMentionQuery("@分", 0, "分", "分析师")).toEqual({
      text: "@分析师 ",
      cursor: 5,
    });
  });

  it("keeps surrounding text", () => {
    expect(replaceMentionQuery("请 @fen 看", 2, "fen", "分析师").text).toBe(
      "请 @分析师 看",
    );
  });
});

describe("mentionedExpertIds / ensureExpertMentions", () => {
  const experts = [
    { agent_id: "a1", name: "分析师" },
    { agent_id: "a2", name: "研究员" },
  ];

  it("lists experts already mentioned in the draft", () => {
    expect(mentionedExpertIds("请 @分析师 看一下", experts)).toEqual(["a1"]);
  });

  it("injects missing mentions when reclaiming a queued turn", () => {
    expect(ensureExpertMentions("帮我看看", ["a2"], experts)).toBe(
      "帮我看看 @研究员 ",
    );
    expect(ensureExpertMentions("@研究员 已有", ["a2"], experts)).toBe(
      "@研究员 已有",
    );
  });
});

describe("mentionedSubagentSlugs", () => {
  it("matches @slug tokens used by the task tool", () => {
    expect(
      mentionedSubagentSlugs("请 @researcher 处理", [
        { slug: "researcher" },
        { slug: "writer" },
      ]),
    ).toEqual(["researcher"]);
  });
});
