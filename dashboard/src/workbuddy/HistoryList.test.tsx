import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WorkBuddyHistoryList } from "../pages/Chat/components/SessionList";

describe("primary sidebar history", () => {
  it("searches current-agent titles, loads the full list once, and preserves selection scope", async () => {
    const onSelect = vi.fn();
    const onFetchAllSessions = vi.fn();
    render(
      <WorkBuddyHistoryList
        sessions={[
          {
            id: "one",
            threadId: "one",
            name: "Design notes",
            channelType: "ui",
            updatedAt: null,
            pinned: true,
          },
          {
            id: "two",
            threadId: "two",
            name: "Research",
            channelType: "ui",
            updatedAt: null,
          },
        ]}
        activeId="one"
        activeAgentId="current-agent"
        hasMore={false}
        loadingMore={false}
        onLoadMore={() => {}}
        onFetchAllSessions={onFetchAllSessions}
        onSelect={onSelect}
        onDelete={() => {}}
        onRename={() => {}}
        onPin={() => {}}
        onFork={() => {}}
      />,
    );
    await userEvent.type(
      screen.getByRole("searchbox", { name: "workbuddy.searchTaskTitles" }),
      "research",
    );
    expect(onFetchAllSessions).toHaveBeenCalledOnce();
    expect(screen.queryByText("Design notes")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Research/ }));
    expect(onSelect).toHaveBeenCalledExactlyOnceWith("two", "current-agent");
    onSelect.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    expect(onSelect).not.toHaveBeenCalled();
  });
});
