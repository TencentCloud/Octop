import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OctopAgent } from "../../../context/AgentContext";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  refresh: vi.fn(),
  role: "member" as string | null,
}));
vi.mock("../../../api/request", () => ({ request: mocks.request }));
vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({ setActiveAgent: vi.fn(), refresh: mocks.refresh }),
}));
vi.mock("../../../hooks/useUserRole", () => ({
  useUserRole: () => mocks.role,
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("../../Agent/Workspace/components/WorkspaceDrawer", () => ({
  default: () => null,
}));
vi.mock("./SubagentCatalogDrawer", () => ({ default: () => null }));
vi.mock("./SkillCatalogDrawer", () => ({ default: () => null }));
vi.mock("./ChannelCatalogDrawer", () => ({ default: () => null }));
vi.mock("./MemoryCatalogDrawer", () => ({ default: () => null }));
vi.mock("./MbtiCatalogDrawer", () => ({ default: () => null }));
vi.mock("./ToolCatalogDrawer", () => ({ default: () => null }));
vi.mock("./PluginCatalogDrawer", () => ({ default: () => null }));
vi.mock("./PublishTemplateButton", () => ({ default: () => null }));
vi.mock("./AgentMoreActions", () => ({ default: () => null }));
vi.mock("./iconForName", () => ({ ExpertIcon: () => null }));
vi.mock("../../Chat/components/RemoteExpertHint", () => ({
  default: () => null,
}));

import { AgentCard } from "./AgentCard";
import { TeamCard } from "./TeamCard";

function agent(state: string, isOwner = false): OctopAgent {
  return {
    agent_id: "shared",
    name: "Shared expert",
    state,
    is_shared: true,
    is_owner: isOwner,
    last_error: null,
  } as OctopAgent;
}

function card(kind: "expert" | "team", row: OctopAgent) {
  const props = {
    agent: row,
    onEdit: vi.fn(),
    onDeleted: vi.fn(),
    onStateChange: vi.fn(),
  };
  return kind === "expert" ? (
    <AgentCard {...props} />
  ) : (
    <TeamCard {...props} experts={[]} />
  );
}

async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(6000);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.role = "member";
  mocks.request.mockReset().mockResolvedValue({
    state: "starting",
    memory_maintenance: { phase: "queued" },
  });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("expert card status permissions", () => {
  it.each(["running", "starting", "stopping"])(
    "does not poll a shared viewer's %s expert",
    async (state) => {
      render(card("expert", agent(state)));
      await tick();
      expect(mocks.request).not.toHaveBeenCalled();
    },
  );
  it("does not poll a shared viewer's starting team", async () => {
    render(card("team", agent("starting")));
    await tick();
    expect(mocks.request).not.toHaveBeenCalled();
  });
  it.each(["expert", "team"] as const)(
    "keeps owner polling for a starting %s",
    async (kind) => {
      render(card(kind, agent("starting", true)));
      await tick();
      expect(mocks.request).toHaveBeenCalledWith("/agents/shared/status");
    },
  );
  it("keeps owner memory-maintenance polling", async () => {
    render(card("expert", agent("running", true)));
    await tick();
    expect(mocks.request).toHaveBeenCalledWith("/agents/shared/status");
  });
  it.each(["expert", "team"] as const)(
    "allows administrators to poll a non-owned %s",
    async (kind) => {
      mocks.role = "admin";
      render(card(kind, agent("starting")));
      await tick();
      expect(mocks.request).toHaveBeenCalledWith("/agents/shared/status");
    },
  );
  it("cleans up maintenance polling when ownership is revoked", async () => {
    const view = render(card("expert", agent("running", true)));
    await tick();
    expect(mocks.request).toHaveBeenCalled();
    view.rerender(card("expert", agent("running")));
    mocks.request.mockClear();
    await tick();
    expect(mocks.request).not.toHaveBeenCalled();
  });
});
