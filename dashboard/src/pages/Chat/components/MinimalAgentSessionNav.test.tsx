import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OctopAgent } from "../../../context/AgentContext";
import {
  getSnapshot,
  ingestHarnessChunk,
  removeSession,
  setSessionTeamRoom,
} from "../hooks/chatStore";
import type { Session } from "../hooks/useSessions";
import MinimalAgentSessionNav from "./MinimalAgentSessionNav";

vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: {
    list: vi.fn().mockResolvedValue([
      {
        thread_id: "team-working-session",
        title: "Team session",
        last_active: 1,
        has_messages: true,
      },
    ]),
    delete: vi.fn().mockResolvedValue(undefined),
    rename: vi.fn().mockResolvedValue(undefined),
    patch: vi.fn().mockResolvedValue(undefined),
  },
}));

const SESSION_ID = "team-working-session";

const agent: OctopAgent = {
  id: 1,
  agent_id: "team-1",
  name: "Cardiology team",
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
  kind: "team",
  member_ids: ["doctor"],
};

const session: Session = {
  id: SESSION_ID,
  name: "Team session",
  threadId: SESSION_ID,
  updatedAt: null,
  channelType: "dashboard",
  hasActivity: true,
};

describe("MinimalAgentSessionNav", () => {
  beforeEach(() => {
    setSessionTeamRoom(SESSION_ID, true);
  });

  afterEach(() => {
    removeSession(SESSION_ID);
  });

  it("keeps a team session marked working until its member finishes", async () => {
    render(
      <MemoryRouter>
        <MinimalAgentSessionNav
          agents={[agent]}
          activeId={SESSION_ID}
          activeAgentId={agent.agent_id}
          activeSessions={[session]}
          onSelect={vi.fn()}
          onAgentSelect={vi.fn()}
          onNewChat={vi.fn()}
          onDeleteActive={vi.fn()}
          onRenameActive={vi.fn()}
          onPinActive={vi.fn()}
          onFork={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Team session")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("chat.sessionWorking"),
    ).not.toBeInTheDocument();

    act(() => {
      ingestHarnessChunk(SESSION_ID, {
        type: "token",
        content: "I will ask the doctor.",
      });
      ingestHarnessChunk(SESSION_ID, {
        type: "token",
        content: "Please rest.",
        agent_id: "doctor",
      });
      ingestHarnessChunk(SESSION_ID, { type: "done" });
    });

    expect(getSnapshot(SESSION_ID).isStreaming).toBe(false);
    await waitFor(() => {
      expect(screen.getByLabelText("chat.sessionWorking")).toBeInTheDocument();
    });

    act(() => {
      ingestHarnessChunk(SESSION_ID, { type: "done", agent_id: "doctor" });
    });

    await waitFor(() => {
      expect(
        screen.queryByLabelText("chat.sessionWorking"),
      ).not.toBeInTheDocument();
    });
  });
});
