import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChannelCard } from "./ChannelCard";

vi.mock("../../../../workbuddy/variant", () => ({ WORKBUDDY_UI: true }));

function props() {
  return {
    channelKey: "telegram" as const,
    enabled: true,
    hasChannel: true,
    isHover: false,
    onClick: vi.fn(),
    onMouseEnter: vi.fn(),
    onMouseLeave: vi.fn(),
    onToggleEnabled: vi.fn(),
  };
}

describe("channel controls in the source card", () => {
  it("opens with the keyboard and toggles without reopening the settings", async () => {
    const callbacks = props();
    render(<ChannelCard {...callbacks} />);
    screen.getByRole("button").focus();
    await userEvent.keyboard("{Enter}");
    expect(callbacks.onClick).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole("switch"));
    expect(callbacks.onToggleEnabled).toHaveBeenCalledWith("telegram", false);
    expect(callbacks.onClick).toHaveBeenCalledOnce();
  });

  it("requires configuration before enablement and keeps settings reachable", async () => {
    const callbacks = { ...props(), enabled: false, hasChannel: false };
    render(<ChannelCard {...callbacks} />);
    expect(screen.getByRole("switch")).toBeDisabled();
    await userEvent.click(screen.getByRole("button"));
    expect(callbacks.onClick).toHaveBeenCalledOnce();
    expect(callbacks.onToggleEnabled).not.toHaveBeenCalled();
  });

  it("distinguishes an enabled channel from a confirmed connection", () => {
    const { rerender } = render(<ChannelCard {...props()} />);
    expect(screen.getByText("channels.channelEnabled")).toBeInTheDocument();
    expect(screen.queryByText("channels.connected")).not.toBeInTheDocument();
    rerender(
      <ChannelCard
        {...props()}
        runtime={{ connected: false, error: "unreachable" }}
      />,
    );
    expect(screen.getByText("channels.disconnected")).toBeInTheDocument();
    expect(screen.queryByText("channels.connected")).not.toBeInTheDocument();
  });
});
