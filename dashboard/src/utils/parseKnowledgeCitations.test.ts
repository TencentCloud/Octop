import { parseKnowledgeCitations } from "./parseKnowledgeCitations";

describe("parseKnowledgeCitations", () => {
  it("returns plain text when no marker", () => {
    expect(parseKnowledgeCitations("hello")).toEqual({
      text: "hello",
      citations: [],
    });
  });

  it("extracts citations and strips the marker", () => {
    const raw =
      'passages\n\n<!--octop-kb-citations:[{"kb_id":"kb1","kb_name":"Docs","doc_id":"d1","filename":"a.md"}]-->';
    expect(parseKnowledgeCitations(raw)).toEqual({
      text: "passages",
      citations: [
        {
          kbId: "kb1",
          kbName: "Docs",
          docId: "d1",
          filename: "a.md",
        },
      ],
    });
  });

  it("dedupes by doc id", () => {
    const raw =
      'x<!--octop-kb-citations:[{"doc_id":"d1","filename":"a.md"},{"doc_id":"d1","filename":"a.md"}]-->';
    expect(parseKnowledgeCitations(raw).citations).toHaveLength(1);
  });
});
