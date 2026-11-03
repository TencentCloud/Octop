import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AgentUnreadBadge from "./AgentUnreadBadge";

describe("AgentUnreadBadge", () => {
  it("opens unread messages without triggering the surrounding expert row", () => {
    const onClick = vi.fn();
    const onRowClick = vi.fn();

    render(
      <div onClick={onRowClick}>
        <AgentUnreadBadge count={3} onClick={onClick} />
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "未读消息" }));

    expect(onClick).toHaveBeenCalledOnce();
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("caps the displayed count at 99+", () => {
    render(<AgentUnreadBadge count={120} onClick={() => undefined} />);
    expect(screen.getByText("99+")).toBeInTheDocument();
  });
});
