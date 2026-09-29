/**
 * T-38 acceptance — the read-only "scope" visibility layer.
 *
 * One test per exit criterion the user fixed, plus the two negative rules this
 * card must not break:
 *
 * * ① the switcher changes the **requested** namespace (asserted on the request);
 * * ② data      → rows render, each tagged with the layer it came from;
 * * ③ no data   → an empty state, **not** an error;
 * * ④ agent-only→ the row says so out loud (R19);
 * * 403         → a permission state, never a page crash (task-54);
 * * zero writes → no write verb anywhere in the new read-visibility source.
 *
 * The panel is presentational, so most cases need no mocking at all.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectMemoryPanel, {
  type ScopePanelGroup,
} from "../../../components/ProjectMemoryPanel";

vi.mock("./memoryScopes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./memoryScopes")>();
  return {
    ...actual,
    fetchMemoryScopes: vi.fn(),
  };
});

vi.mock("../../../api/modules/teams", () => ({
  teamsApi: { list: vi.fn().mockResolvedValue([]) },
}));

import ScopedMemoryView from "./ScopedMemoryView";
import { fetchMemoryScopes } from "./memoryScopes";

const fetchMock = vi.mocked(fetchMemoryScopes);

function group(
  layer: string,
  namespace: string,
  texts: string[],
): ScopePanelGroup {
  return {
    source_layer: layer,
    namespace,
    total: texts.length,
    items: texts.map((text, i) => ({
      id: `${layer}-${i}`,
      text,
      source_layer: layer,
      namespace,
    })),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("T-38 ③ empty state", () => {
  it("renders an empty state — not an error — when a layer has no memory", () => {
    render(<ProjectMemoryPanel groups={[]} scope="project" />);
    expect(screen.getByTestId("memory-scope-empty")).toBeTruthy();
    expect(screen.queryByTestId("memory-scope-error")).toBeNull();
  });

  it("treats a group that exists but carries zero rows as empty too", () => {
    render(
      <ProjectMemoryPanel groups={[group("project", "project_P1", [])]} />,
    );
    expect(screen.getByTestId("memory-scope-empty")).toBeTruthy();
  });
});

describe("T-38 ② rows render with their source layer", () => {
  it("renders every row and tags it with the layer it came from", () => {
    render(
      <ProjectMemoryPanel
        scope="project"
        groups={[
          group("project", "project_P1", ["项目层的事实 A"]),
          group("team", "team_T1", ["团队层的事实 B"]),
        ]}
      />,
    );
    expect(screen.getByTestId("memory-scope-panel")).toBeTruthy();
    expect(screen.getAllByTestId("memory-scope-item")).toHaveLength(2);
    expect(screen.getByText("项目层的事实 A")).toBeTruthy();
    expect(screen.getByText("团队层的事实 B")).toBeTruthy();
    // Each row carries an explicit provenance tag.
    expect(screen.getAllByTestId("memory-scope-tag-project")).toHaveLength(1);
    expect(screen.getAllByTestId("memory-scope-tag-team")).toHaveLength(1);
    expect(screen.getByTestId("memory-scope-group-project")).toBeTruthy();
    expect(screen.getByTestId("memory-scope-group-team")).toBeTruthy();
  });
});

describe("T-38 ④ / R19 agent-only annotation", () => {
  it("marks agent-layer rows as not yet in the team or project layer", () => {
    render(
      <ProjectMemoryPanel
        scope="agent"
        groups={[
          group("project", "project_P1", ["已进项目"]),
          group("agent", "agent_a1", ["只在私有层"]),
        ]}
      />,
    );
    const notes = screen.getAllByTestId("memory-scope-agent-only");
    expect(notes).toHaveLength(1);
    expect(notes[0].textContent).toContain("agent");
    // The project-layer row must NOT carry the agent-only note.
    const projectRow = screen
      .getAllByTestId("memory-scope-item")
      .find((el) => el.getAttribute("data-layer") === "project");
    expect(
      projectRow?.querySelector('[data-testid="memory-scope-agent-only"]'),
    ).toBeNull();
  });
});

describe("T-38 permission state (task-54 403)", () => {
  it("renders a permission state instead of crashing when the project is refused", () => {
    render(<ProjectMemoryPanel groups={[]} scope="project" denied />);
    expect(screen.getByTestId("memory-scope-denied")).toBeTruthy();
    expect(screen.queryByTestId("memory-scope-error")).toBeNull();
    expect(screen.queryByTestId("memory-scope-panel")).toBeNull();
  });

  it("lets 403 outrank content: a refused read never renders rows", () => {
    render(
      <ProjectMemoryPanel
        scope="project"
        denied
        groups={[group("project", "project_P1", ["不该出现"])]}
      />,
    );
    expect(screen.queryByText("不该出现")).toBeNull();
    expect(screen.getByTestId("memory-scope-denied")).toBeTruthy();
  });

  it("shows a retryable error for failures that are not a permission denial", () => {
    render(<ProjectMemoryPanel groups={[]} error="boom" onRetry={() => {}} />);
    expect(screen.getByTestId("memory-scope-error")).toBeTruthy();
  });
});

describe("T-38 ① the switcher changes the requested namespace", () => {
  it("asks for no project/team layer in the agent scope", async () => {
    fetchMock.mockResolvedValue({ agent_id: "a1", groups: [] });
    render(<ScopedMemoryView agentId="a1" scope="team" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("a1", {
      projectId: null,
      teamId: null,
    });
  });

  it("adds project_id once a project is selected", async () => {
    fetchMock.mockResolvedValue({ agent_id: "a1", groups: [] });
    render(<ScopedMemoryView agentId="a1" scope="project" projectId="P1" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("a1", {
      projectId: "P1",
      teamId: null,
    });
  });

  it("never guesses a project: with no project chosen it issues no request", async () => {
    render(<ScopedMemoryView agentId="a1" scope="project" projectId={null} />);
    expect(screen.getByTestId("memory-scope-empty")).toBeTruthy();
    await waitFor(() => expect(fetchMock).not.toHaveBeenCalled());
  });

  it("turns a 403 into the permission state rather than an error banner", async () => {
    fetchMock.mockRejectedValue(
      new Error('403 {"error":{"code":"PROJECT_FORBIDDEN"}}'),
    );
    render(<ScopedMemoryView agentId="a1" scope="project" projectId="P9" />);
    await waitFor(() =>
      expect(screen.getByTestId("memory-scope-denied")).toBeTruthy(),
    );
    expect(screen.queryByTestId("memory-scope-error")).toBeNull();
  });
});

describe("T-38 zero write action (SPEC B38)", () => {
  const here = (rel: string) =>
    readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

  it("the read-visibility source contains no write verb", () => {
    // A write path here would turn "can see" into "can write" — the exact
    // boundary B38 draws, and T-41/P2 owns the write half.
    const banned = [
      /method:\s*["'](POST|PUT|PATCH|DELETE)["']/i,
      /\b(createAtom|replaceAtom|promoteCandidate|addAtom)\b/,
      /记到项目/,
    ];
    for (const rel of ["./memoryScopes.ts", "./ScopedMemoryView.tsx"]) {
      const src = here(rel);
      for (const pattern of banned) {
        expect(src, `${rel} must not match ${pattern}`).not.toMatch(pattern);
      }
    }
  });
});
