import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import i18n from "../i18n";
import type { OctopAgent } from "../context/AgentContext";

vi.mock("../api/request", () => ({
  request: vi.fn(async (path: string) => {
    if (path.endsWith("/skills")) {
      return [{ slug: "demo-skill", name: "Demo skill", kind: "workspace" }];
    }
    return { name: "Demo agent", description: "Description" };
  }),
}));

vi.mock("../api/modules/subagents", () => ({
  listAgentSubagents: vi.fn(async () => [
    {
      slug: "demo-subagent",
      name: "Demo subagent",
      description: "Subagent description",
    },
  ]),
}));

vi.mock("../pages/Experts/components/expertFileGroups", () => ({
  fetchConfigMdFiles: vi.fn(async () => ["SOUL.md"]),
}));

vi.mock("../pages/Agent/Skills/skillDisplayNames", () => ({
  useSkillDisplayName: () => (skill: { name: string }) => skill.name,
}));

vi.mock("../pages/Experts/components/SkillCatalogDrawer", () => ({
  default: () => null,
}));

vi.mock("../pages/Experts/components/SubagentCatalogDrawer", () => ({
  default: () => null,
}));

vi.mock("../pages/Agent/Workspace/components/WorkspaceDrawer", () => ({
  default: () => null,
}));

import AgentProfileDrawer from "./AgentProfileDrawer";

const agent = {
  agent_id: "agent-1",
  name: "Demo agent",
  state: "running",
} as OctopAgent;

describe("AgentProfileDrawer sections", () => {
  const getComputedStyle = window.getComputedStyle;

  beforeAll(() => {
    vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
      getComputedStyle(element),
    );
  });

  afterAll(() => {
    vi.restoreAllMocks();
  });

  it("allows config, skill, and subagent sections to collapse independently", async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AgentProfileDrawer open agent={agent} onClose={vi.fn()} />
      </I18nextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("SOUL.md")).toBeInTheDocument();
      expect(screen.getByText("Demo skill")).toBeInTheDocument();
      expect(screen.getByText("Demo subagent")).toBeInTheDocument();
    });

    const configHeader = screen
      .getByText("experts.configFiles")
      .closest(".ant-collapse-header");
    const skillHeader = screen
      .getByText("experts.skillFilesTitle")
      .closest(".ant-collapse-header");
    const subagentHeader = screen
      .getByText("experts.subagentFilesTitle")
      .closest(".ant-collapse-header");

    expect(configHeader).not.toBeNull();
    expect(skillHeader).not.toBeNull();
    expect(subagentHeader).not.toBeNull();

    fireEvent.click(configHeader!);
    expect(configHeader).toHaveAttribute("aria-expanded", "false");
    expect(skillHeader).toHaveAttribute("aria-expanded", "true");
    expect(subagentHeader).toHaveAttribute("aria-expanded", "true");
  });
});
