import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import SessionList from "./SessionList";

function renderList(props: { unreadyExperts?: number } = {}) {
  render(
    <MemoryRouter>
      <SessionList
        agents={[]}
        unreadyExperts={props.unreadyExperts}
        sessions={[]}
        activeId={null}
        activeAgentId={null}
        hasMore={false}
        loadingMore={false}
        onLoadMore={() => undefined}
        onFetchAllSessions={() => undefined}
        onSelect={() => undefined}
        onAgentSelect={() => undefined}
        onNewChat={() => undefined}
        onDelete={() => undefined}
        onRename={() => undefined}
        onPin={() => undefined}
        onFork={() => undefined}
      />
    </MemoryRouter>,
  );
}

/**
 * The history rail lists only experts that can chat, so an empty list means
 * either "no experts" or "none running". Telling someone with a half-configured
 * expert to "create your first AI expert" hides the one they already have.
 */
describe("SessionList empty experts", () => {
  beforeEach(() => {
    vi.spyOn(octopThreadsApi, "list").mockResolvedValue([]);
  });

  it("invites a first expert when the user owns none", () => {
    renderList();

    expect(screen.getByText("chat.noAgentsHint")).toBeInTheDocument();
    expect(screen.getByText("chat.createExpert")).toBeInTheDocument();
    expect(screen.queryByText("chat.noChattableAgentsHint")).toBeNull();
  });

  it("points at the experts page when they own one that cannot chat", () => {
    renderList({ unreadyExperts: 1 });

    expect(screen.getByText("chat.noChattableAgentsHint")).toBeInTheDocument();
    expect(screen.getByText("chat.goToExperts")).toBeInTheDocument();
    expect(screen.queryByText("chat.noAgentsHint")).toBeNull();
  });
});
