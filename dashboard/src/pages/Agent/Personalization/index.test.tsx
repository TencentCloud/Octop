/**
 * Personalization must only show and edit an expert the user owns (#1097):
 * other users' shared experts come first in the agent list and can be the
 * active selection for an account that owns none.
 */

import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

type TestAgent = {
  agent_id: string;
  name: string;
  is_shared?: boolean;
  is_owner?: boolean;
  state?: string;
};

const agentState: {
  agents: TestAgent[];
  activeAgentId: string | null;
  loading: boolean;
} = { agents: [], activeAgentId: null, loading: false };

const navigate = vi.fn();

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => agentState,
}));

vi.mock("../../../hooks/useIsMobile", () => ({ useIsMobile: () => false }));

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ username: "newbie" }),
}));

vi.mock("../../../utils/permissions", () => ({ userCan: () => true }));

vi.mock("../../../hooks/usePathTabs", () => ({
  usePathTabs: () => ({
    activeTab: "skills",
    handleTabChange: vi.fn(),
    isMounted: () => true,
  }),
}));

vi.mock("../../../layouts/PageShell", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  pageShellStyles: {},
}));

function panel(name: string) {
  return {
    default: ({ agentId }: { agentId?: string | null }) => (
      <div>{`${name}:${agentId ?? "none"}`}</div>
    ),
  };
}

vi.mock("../Skills/components/SkillsTabs", () => panel("skills"));
vi.mock("../Tools/ToolsTabs", () => panel("tools"));
vi.mock("./components/AgentPluginsPanel", () => panel("plugins"));
vi.mock("../../Experts/components/SubagentManager", () => panel("subagents"));
vi.mock("./components/MBTISelector", () => panel("mbti"));
vi.mock("../Memory/MemoryPanel", () => panel("memory"));
vi.mock("../Channels/ChannelsPanel", () => panel("channels"));

import PersonalizationPage from "./index";

const sharedByOther: TestAgent = {
  agent_id: "shared-1",
  name: "Someone else's expert",
  is_shared: true,
  is_owner: false,
};
const mine: TestAgent = {
  agent_id: "mine-1",
  name: "My expert",
  is_owner: true,
};

describe("PersonalizationPage expert ownership", () => {
  beforeEach(() => {
    navigate.mockReset();
    agentState.loading = false;
  });

  it("offers to create an expert instead of showing a shared one", () => {
    agentState.agents = [sharedByOther];
    agentState.activeAgentId = sharedByOther.agent_id;

    render(<PersonalizationPage />);

    expect(screen.getByText("chat.noAgentsTitle")).toBeInTheDocument();
    expect(screen.queryByText(/shared-1/)).not.toBeInTheDocument();
    screen.getByRole("button", { name: "chat.createExpert" }).click();
    expect(navigate).toHaveBeenCalledWith("/experts");
  });

  it("never hands a shared expert to the panels", () => {
    agentState.agents = [sharedByOther, mine];
    agentState.activeAgentId = sharedByOther.agent_id;

    render(<PersonalizationPage />);

    expect(screen.getByText("skills:none")).toBeInTheDocument();
    expect(screen.queryByText(/shared-1/)).not.toBeInTheDocument();
  });

  it("uses the selected expert when the user owns it", () => {
    agentState.agents = [sharedByOther, mine];
    agentState.activeAgentId = mine.agent_id;

    render(<PersonalizationPage />);

    for (const name of ["skills", "tools", "plugins", "memory", "channels"]) {
      expect(screen.getAllByText(`${name}:mine-1`).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("subagents:mine-1")).toBeInTheDocument();
    expect(screen.getByText("mbti:mine-1")).toBeInTheDocument();
  });

  it("does not flash the empty state while experts are loading", () => {
    agentState.agents = [];
    agentState.activeAgentId = null;
    agentState.loading = true;

    render(<PersonalizationPage />);

    expect(screen.queryByText("chat.noAgentsTitle")).not.toBeInTheDocument();
  });
});
