/**
 * #1849: the experts table must not offer deleting peer (bridge) experts.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => vi.fn(),
}));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({ agents: [], setActiveAgent: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("../../../api/request", () => ({ request: vi.fn() }));

// useServerTimezone fires on mount; a pending promise keeps it from touching state.
vi.mock("../../../api/modules/settings", () => ({
  octopSettingsApi: { timezone: () => new Promise(() => {}) },
}));

// jsdom has no DOMMatrix; keep pdfjs (pulled in via WorkspaceDrawer) out of the import chain.
vi.mock("react-pdf", () => ({
  Document: () => null,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

import AgentExpertsTable from "./AgentExpertsTable";
import type { OctopAgent } from "../../../context/AgentContext";

function agent(overrides: Partial<OctopAgent>): OctopAgent {
  return {
    id: 1,
    agent_id: "01ABC",
    name: "Expert",
    description: null,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: null,
    state: "running",
    last_error: null,
    icon: null,
    icon_name: null,
    icon_url: null,
    color: null,
    config: {},
    is_owner: true,
    ...overrides,
  };
}

describe("<AgentExpertsTable /> peer expert delete guard", () => {
  it("hides the delete action for bridge experts but keeps it for local ones", () => {
    render(
      <AgentExpertsTable
        agents={[
          agent({ agent_id: "01LOCAL", name: "Local Expert" }),
          agent({
            agent_id: "bridge:cid:aid",
            name: "Peer Expert",
            bridge: true,
          }),
        ]}
        onEdit={vi.fn()}
        onDeleted={vi.fn()}
        onStateChange={vi.fn()}
      />,
    );

    // Both rows render; only the local expert keeps the delete affordance.
    expect(screen.getByText("Local Expert")).toBeInTheDocument();
    expect(screen.getByText("Peer Expert")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(1);
  });
});
