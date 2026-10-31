import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import ChatSidebarPanel, { EXPAND_CHAT_RAIL_EVENT } from "./ChatSidebarPanel";
import edgeStyles from "../../../components/RailEdgeControl.module.less";

/**
 * The history rail folds from the seam on its right — the same capsule the nav
 * rail uses on its own seam, so both left columns answer to one shape. This
 * keeps the click contract (close, or open-and-broadcast) and the stacking rule
 * pinned to the place it actually lives.
 */
vi.mock("./SessionList", () => ({ default: () => null }));
vi.mock("./MinimalAgentSessionNav", () => ({ default: () => null }));

const noop = () => undefined;

function renderPanel(
  overrides: Partial<ComponentProps<typeof ChatSidebarPanel>> = {},
) {
  const onSidebarOpenChange = vi.fn();
  render(
    <ChatSidebarPanel
      isMobile={false}
      sidebarOpen
      sidebarWidth={260}
      agents={[]}
      sessions={[]}
      activeThreadId={null}
      resolvedAgentId={null}
      sessionsHasMore={false}
      sessionsLoadingMore={false}
      onLoadMoreSessions={noop}
      onFetchAllSessions={noop}
      onSelectSession={noop}
      onAgentSelect={noop}
      onNewChatWithAgent={noop}
      onDeleteSession={noop}
      onRenameSession={noop}
      onPinSession={noop}
      onForkSession={noop}
      onSidebarOpenChange={onSidebarOpenChange}
      onSidebarResizeStart={noop}
      {...overrides}
    />,
  );
  return { onSidebarOpenChange };
}

/** The seam handle is the rail's only control — no header glyph anymore. */
function seamHandle(name: RegExp) {
  const matches = screen.getAllByRole("button", { name });
  expect(matches).toHaveLength(1);
  return matches[0];
}

describe("history rail seam handle", () => {
  it("collapses the rail without leaving the page", async () => {
    const user = userEvent.setup();
    const broadcast = vi.fn();
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, broadcast);
    const { onSidebarOpenChange } = renderPanel({ sidebarOpen: true });

    const button = seamHandle(/展开对话历史|收起对话历史/);
    expect(button).toHaveAccessibleName("收起对话历史");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+Shift+B");
    expect(button.getAttribute("title")).toMatch(/收起对话历史 \(.+Shift\+B\)/);

    await user.click(button);
    expect(onSidebarOpenChange).toHaveBeenCalledWith(false);
    expect(broadcast).not.toHaveBeenCalled();

    window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, broadcast);
  });

  it("broadcasts on expand so a collapsed nav rail comes back with it", async () => {
    const user = userEvent.setup();
    const broadcast = vi.fn();
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, broadcast);
    const { onSidebarOpenChange } = renderPanel({ sidebarOpen: false });

    const button = seamHandle(/展开对话历史|收起对话历史/);
    expect(button).toHaveAccessibleName("展开对话历史");
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    // Two rails collapsed: this one click brings back both.
    expect(broadcast).toHaveBeenCalledTimes(1);
    expect(onSidebarOpenChange).toHaveBeenCalledWith(true);

    window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, broadcast);
  });

  it("stays painted and stacks below the nav handle while collapsed", () => {
    renderPanel({ sidebarOpen: false });
    const button = seamHandle(/展开对话历史/);
    expect(button).toHaveClass(edgeStyles.btnPersistent);
    // Collapsed, this seam is the nav's divider — the nav handle takes the top slot.
    expect(button).toHaveClass(edgeStyles.btnBottom);
  });

  it("centres on its own seam while expanded", () => {
    renderPanel({ sidebarOpen: true });
    const button = seamHandle(/收起对话历史/);
    expect(button).not.toHaveClass(edgeStyles.btnPersistent);
    expect(button).not.toHaveClass(edgeStyles.btnBottom);
  });

  it("is absent where there is no rail of its own to fold", () => {
    // Minimal layout embeds the list inside the nav pane; mobile uses a drawer.
    renderPanel({ navEmbedded: true });
    expect(
      screen.queryByRole("button", { name: /展开对话历史|收起对话历史/ }),
    ).not.toBeInTheDocument();

    renderPanel({ isMobile: true, sidebarOpen: false });
    expect(
      screen.queryByRole("button", { name: /展开对话历史|收起对话历史/ }),
    ).not.toBeInTheDocument();
  });
});
