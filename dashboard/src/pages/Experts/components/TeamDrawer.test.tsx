import { App } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { OctopAgent } from "../../../context/AgentContext";
import { teamsApi } from "../../../api/modules/teams";
import TeamDrawer from "./TeamDrawer";

const { t } = vi.hoisted(() => ({ t: (key: string) => key }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t }) }));
vi.mock("../../../hooks/useAgentFormResources", () => ({
  useAgentFormResources: () => ({
    models: [{ provider_name: "test", model: "model", name: "Model" }],
    modelsLoading: false,
    backends: [],
    backendsLoading: false,
  }),
}));
vi.mock("../../../api/modules/teams", () => ({
  teamsApi: { templateFiles: vi.fn(), get: vi.fn(), update: vi.fn() },
}));

function expert(id: string, state: string): OctopAgent {
  return {
    id: 1,
    agent_id: id,
    name: id,
    state,
    is_owner: true,
    description: null,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: null,
    last_error: null,
    icon: null,
    icon_name: null,
    icon_url: null,
    color: null,
    config: {},
  };
}
const experts = [
  expert("Running", "running"),
  expert("Stopped", "stopped"),
  expert("Failed", "failed"),
];
const record = {
  team_id: "team",
  agent_id: "team",
  name: "Team",
  kind: "team" as const,
  member_ids: ["Running", "Stopped"],
  members: experts
    .slice(0, 2)
    .map(({ agent_id, name, state }) => ({ agent_id, name, state })),
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(teamsApi.templateFiles).mockResolvedValue([]);
  vi.mocked(teamsApi.get).mockResolvedValue(record);
  vi.mocked(teamsApi.update).mockResolvedValue(record);
});

it("offers only running experts when creating a team", async () => {
  render(
    <App>
      <TeamDrawer
        open
        mode="create"
        experts={experts}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    </App>,
  );
  await screen.findByRole("button", { name: /Running/ });
  expect(
    screen.queryByRole("button", { name: /Stopped/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Failed/ }),
  ).not.toBeInTheDocument();
});

it("preserves an existing stopped member when editing a team", async () => {
  render(
    <App>
      <TeamDrawer
        open
        mode="edit"
        team={{
          ...expert("team", "running"),
          name: "Team",
          kind: "team",
          member_ids: record.member_ids,
        }}
        experts={experts}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    </App>,
  );
  const stopped = await screen.findByRole("button", { name: /Stopped/ });
  await waitFor(() => expect(stopped).toHaveAttribute("aria-pressed", "true"));
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() => expect(teamsApi.update).toHaveBeenCalled());
  expect(vi.mocked(teamsApi.update).mock.calls[0][1].member_ids).toEqual(
    record.member_ids,
  );
});
