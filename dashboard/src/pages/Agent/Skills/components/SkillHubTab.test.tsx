import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../../../../api/request", () => ({ request: vi.fn() }));

import { request } from "../../../../api/request";
import SkillHubTab from "./SkillHubTab";

const mockedRequest = vi.mocked(request);

/**
 * The SkillHub showcase/search APIs rank one *package* per namespace, so the
 * same public ``slug`` can appear several times (e.g. ``@a/libai`` and
 * ``@b/libai``). These fixtures mirror that upstream shape, including entries
 * whose ``name`` is empty or the bare slug.
 */
function rankingsResponse() {
  return {
    rankings: {
      recommended: {
        section: "recommended",
        total: 5,
        skills: [
          {
            slug: "parenting-expert",
            name: "育儿大师.Skill",
            description: "家庭教育支持",
            downloads: 2030505,
          },
          {
            slug: "parenting-expert",
            name: "育儿大师.Skill",
            description: "家庭教育支持",
            downloads: 2030505,
          },
          {
            slug: "libai",
            name: "李白.Skill",
            description: "润色专家",
            downloads: 777033,
          },
          {
            slug: "libai",
            name: "libai-skill",
            description: "润色专家",
            downloads: 585194,
          },
          {
            slug: "dev-expert",
            name: "",
            display_name_zh: "编程专家",
            description: "编程助手",
            downloads: 2663108,
          },
          {
            slug: "smart-charts",
            name: "",
            description: "图表生成",
            downloads: 426742,
          },
        ],
      },
    },
  };
}

describe("<SkillHubTab />", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders each upstream slug only once in a ranking section", async () => {
    mockedRequest.mockResolvedValue(rankingsResponse());

    render(<SkillHubTab target={{ type: "browse" }} />);

    // First (best-ranked) entry of the slug pair survives.
    expect(await screen.findByText("李白.Skill")).toBeInTheDocument();
    // Its lower-ranked same-slug twin is dropped.
    expect(screen.queryByText("libai-skill")).not.toBeInTheDocument();
    // Exact duplicates from the upstream payload collapse to one card.
    expect(screen.getAllByText("育儿大师.Skill")).toHaveLength(1);
  });

  it("falls back to display name or slug when the entry name is empty", async () => {
    mockedRequest.mockResolvedValue(rankingsResponse());

    render(<SkillHubTab target={{ type: "browse" }} />);

    expect(await screen.findByText("编程专家")).toBeInTheDocument();
    // No localized/display name either: the slug keeps the card titled.
    expect(screen.getByText("smart-charts")).toBeInTheDocument();
  });
});
