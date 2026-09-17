import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatTitleBar from "./ChatTitleBar";
import type { Session } from "../hooks/useSessions";
import {
  loadExpandProcessWhileStreaming,
  PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY,
} from "../utils/chatStorage";

const session: Session = {
  id: "s1",
  name: "Weekly recap",
  threadId: "t1",
  updatedAt: null,
  channelType: "web",
};

const noop = vi.fn();

describe("ChatTitleBar", () => {
  beforeEach(() => {
    localStorage.removeItem(PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY);
  });

  it("keeps the more menu beside the title edit control", () => {
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    const heading = screen.getByRole("heading", { name: "Weekly recap" });
    const edit = screen.getByRole("button", { name: "common.edit" });
    const more = screen.getByRole("button", { name: "更多" });

    expect(heading.parentElement).toContainElement(edit);
    expect(heading.parentElement).toContainElement(more);
  });

  it("toggles the expand-process preference from the more menu", async () => {
    const user = userEvent.setup();
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    await user.click(screen.getByRole("button", { name: "更多" }));
    const item = await screen.findByText("生成时展开思考过程");
    expect(loadExpandProcessWhileStreaming()).toBe(false);
    await user.click(item);
    expect(loadExpandProcessWhileStreaming()).toBe(true);
  });

  it("marks the title bar as a Wails drag region", () => {
    const { container } = render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    expect(container.querySelector(".octop-desktop-drag")).not.toBeNull();
  });
});
