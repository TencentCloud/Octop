import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps, ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import ChatSidebarPanel, { EXPAND_CHAT_RAIL_EVENT } from "./ChatSidebarPanel";

/**
 * The history rail folds from its own header (`SessionList`'s `railToggle`
 * slot), not from a second panel glyph stacked in the nav. Rendering the panel
 * here keeps the click contract — close, or open-and-broadcast — pinned to the
 * place it actually lives.
 */
vi.mock("./SessionList", () => ({
  default: ({ railToggle }: { railToggle?: ReactNode }) => (
    <div>{railToggle}</div>
  ),
}));
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

/**
 * The seam pill (`RailEdgeControl`) shares the accessible name — both close the
 * same rail. Only the header control publishes `aria-expanded`, so that is what
 * tells them apart here.
 */
function headerToggle() {
  const matches = screen
    .getAllByRole("button", { name: /展开对话历史|收起对话历史/ })
    .filter((el) => el.hasAttribute("aria-expanded"));
  expect(matches).toHaveLength(1);
  return matches[0];
}

describe("history rail header toggle", () => {
  it("collapses the rail without leaving the page", async () => {
    const user = userEvent.setup();
    const broadcast = vi.fn();
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, broadcast);
    const { onSidebarOpenChange } = renderPanel({ sidebarOpen: true });

    const button = headerToggle();
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

    const button = headerToggle();
    expect(button).toHaveAccessibleName("展开对话历史");
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    expect(broadcast).toHaveBeenCalledTimes(1);
    expect(onSidebarOpenChange).toHaveBeenCalledWith(true);

    window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, broadcast);
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
