import { describe, expect, it } from "vitest";
import { parseOfficePdfMeta } from "./officePreview";

describe("parseOfficePdfMeta", () => {
  it("decodes percent-encoded CJK font names", () => {
    const headers = new Headers({
      "X-Octop-Office-Preview-Digest": "abc",
      "X-Octop-Office-Missing-Fonts": "%E5%AE%8B%E4%BD%93,Noto%20Sans",
    });
    expect(parseOfficePdfMeta(headers)).toEqual({
      digest: "abc",
      missingFonts: ["宋体", "Noto Sans"],
    });
  });

  it("keeps a malformed token instead of throwing", () => {
    const headers = new Headers({
      "X-Octop-Office-Missing-Fonts": "%E5%AE%8B%",
    });
    expect(parseOfficePdfMeta(headers).missingFonts).toEqual(["%E5%AE%8B%"]);
  });
});
