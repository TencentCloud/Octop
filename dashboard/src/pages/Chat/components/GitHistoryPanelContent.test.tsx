import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const gitApi = vi.hoisted(() => ({
  history: vi.fn(),
}));

vi.mock("../../../api/modules/git", () => ({ gitApi }));
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

import GitHistoryPanelContent from "./GitHistoryPanelContent";

const ROWS = [
  {
    graph: "*",
    sha: "a".repeat(40),
    short: "aaaaaaa",
    author: "Alice",
    committer: "Alice",
    date: "2026-01-01T00:00:00Z",
    refs: "HEAD -> main, origin/main",
    signature: "G",
    signer: "Alice",
    subject: "feat: signed work",
  },
  { graph: "|", sha: null },
  {
    graph: "| *",
    sha: "b".repeat(40),
    short: "bbbbbbb",
    author: "Bob",
    committer: "CI Bot",
    date: "2025-12-31T00:00:00Z",
    refs: "",
    signature: "N",
    signer: "",
    subject: "fix: unsigned work",
  },
];

describe("GitHistoryPanelContent", () => {
  it("renders graph rows, refs and signature badges", async () => {
    gitApi.history.mockResolvedValue(ROWS);
    render(<GitHistoryPanelContent agentId="agent-1" />);

    await waitFor(() => {
      expect(screen.getAllByTestId("git-history-row")).toHaveLength(2);
    });
    expect(gitApi.history).toHaveBeenCalledWith("agent-1", 80);
    expect(screen.getByText("feat: signed work")).toBeInTheDocument();
    expect(screen.getByText("fix: unsigned work")).toBeInTheDocument();
    expect(screen.getByText("HEAD -> main")).toBeInTheDocument();
    expect(screen.getByText("verified")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("CI Bot")).toBeInTheDocument();
    expect(screen.getByText("2026-01-01 00:00:00")).toBeInTheDocument();
    expect(screen.getByText("2025-12-31 00:00:00")).toBeInTheDocument();
    const rows = screen.getAllByTestId("git-history-row");
    expect(rows[0]).toHaveAttribute("data-signature", "G");
    expect(rows[1]).toHaveAttribute("data-signature", "N");
  });
});
