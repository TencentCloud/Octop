import { describe, expect, it } from "vitest";
import { resolveSkillDisplayName } from "./skillDisplayNames";

describe("resolveSkillDisplayName", () => {
  it("prefers metadata.octop.label for the UI locale", () => {
    expect(
      resolveSkillDisplayName(
        {
          slug: "tcapi",
          name: "tcapi",
          label: { zh: "腾讯云 API", en: "Tencent Cloud API" },
        },
        "zh",
      ),
    ).toBe("腾讯云 API");
    expect(
      resolveSkillDisplayName(
        {
          slug: "tcapi",
          name: "tcapi",
          label: { zh: "腾讯云 API", en: "Tencent Cloud API" },
        },
        "en",
      ),
    ).toBe("Tencent Cloud API");
  });

  it("falls back to display_name then presentation name", () => {
    expect(
      resolveSkillDisplayName(
        { slug: "tcapi", name: "tcapi", display_name: "腾讯云 API 助手" },
        "zh",
      ),
    ).toBe("腾讯云 API 助手");
    expect(
      resolveSkillDisplayName({ slug: "pdf", name: "PDF 阅读与编辑" }, "zh"),
    ).toBe("PDF 阅读与编辑");
  });

  it("uses the slug when only the identity name is present", () => {
    expect(resolveSkillDisplayName({ slug: "pdf", name: "pdf" }, "zh")).toBe(
      "pdf",
    );
  });
});
