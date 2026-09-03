import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import TrajectoryToolbar from "./TrajectoryToolbar";

describe("TrajectoryToolbar", () => {
  it("toggles duration and search", async () => {
    const user = userEvent.setup();
    const onDurationOnChange = vi.fn();
    const onSearchQueryChange = vi.fn();
    render(
      <TrajectoryToolbar
        durationOn={false}
        onDurationOnChange={onDurationOnChange}
        allTurnsCollapsed={false}
        onToggleAllTurns={() => {}}
        allCallsCollapsed={false}
        onToggleAllCalls={() => {}}
        searchQuery=""
        onSearchQueryChange={onSearchQueryChange}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Duration/i }));
    expect(onDurationOnChange).toHaveBeenCalledWith(true);
    await user.type(screen.getByRole("searchbox"), "read");
    expect(onSearchQueryChange).toHaveBeenCalled();
  });

  it("shows fold icons for turns and calls instead of a selected-filter look", () => {
    const { rerender } = render(
      <TrajectoryToolbar
        durationOn={false}
        onDurationOnChange={() => {}}
        allTurnsCollapsed={false}
        onToggleAllTurns={() => {}}
        allCallsCollapsed={false}
        onToggleAllCalls={() => {}}
        searchQuery=""
        onSearchQueryChange={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /Turns/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: /Calls/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    rerender(
      <TrajectoryToolbar
        durationOn={true}
        onDurationOnChange={() => {}}
        allTurnsCollapsed={true}
        onToggleAllTurns={() => {}}
        allCallsCollapsed={true}
        onToggleAllCalls={() => {}}
        searchQuery=""
        onSearchQueryChange={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /Duration/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Turns/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Calls/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
