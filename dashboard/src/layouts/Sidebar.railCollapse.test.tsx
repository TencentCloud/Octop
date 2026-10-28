import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LayoutModeProvider } from "../context/LayoutModeContext";
import { EXPAND_CHAT_RAIL_EVENT } from "../pages/Chat/components/ChatSidebarPanel";
import { LAYOUT_MODE_KEY } from "./layoutModeStorage";
import Sidebar from "./Sidebar";

vi.mock("../components/AvatarDropdown", () => ({
  default: () => null,
}));
vi.mock("../components/AppVersionBadge", () => ({
  default: () => null,
}));
vi.mock("../components/CurrentVersionBadge", () => ({
  default: () => null,
}));
vi.mock("../hooks/useUpdateStatus", () => ({
  useUpdateStatus: () => ({ hasUpdate: false }),
}));
vi.mock("../hooks/useServerCapabilities", () => ({
  useServerCapabilities: () => ({ mobileEnabled: false, loading: false }),
}));

function renderSidebar(opts: { collapsed: boolean; onToggle?: () => void }) {
  return render(
    <LayoutModeProvider>
      <MemoryRouter initialEntries={["/chat"]}>
        <Sidebar
          selectedKey="chat"
          collapsed={opts.collapsed}
          onToggle={opts.onToggle ?? (() => undefined)}
          isMobile={false}
        />
      </MemoryRouter>
    </LayoutModeProvider>,
  );
}

/**
 * The nav rail used to be collapsible only through a 16px pill that stayed
 * invisible until the pointer happened to cross the seam. The rail's own header
 * now carries the control, so these are the two states worth pinning down.
 */
describe("nav rail collapse control", () => {
  beforeEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
  });

  it("offers a collapse button in the header while expanded", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    renderSidebar({ collapsed: false, onToggle });

    const button = screen.getByRole("button", { name: "收起导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    // The accelerator is advertised, not baked into the name.
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");
    // Tooltip advertises the accelerator.
    expect(button.getAttribute("title")).toMatch(/收起导航栏 \(.+B\)/);

    await user.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("turns the collapsed mark into the expand button", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    renderSidebar({ collapsed: true, onToggle });

    expect(
      screen.queryByRole("button", { name: "收起导航栏" }),
    ).not.toBeInTheDocument();

    const button = screen.getByRole("button", { name: "展开导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");

    await user.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});

/**
 * With the rail collapsed the Chat row's toggle collapses with it, so the
 * history rail needs a control of its own in the icon rail — otherwise the only
 * ways back are a 16px hover sliver and a keyboard shortcut.
 */
describe("history rail control while the nav is collapsed", () => {
  beforeEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
  });

  it("stays reachable from the icon rail", async () => {
    const user = userEvent.setup();
    const onExpand = vi.fn();
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, onExpand);

    renderSidebar({ collapsed: true });

    const button = screen.getByRole("button", { name: "展开对话历史" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+Shift+B");

    await user.click(button);
    expect(onExpand).toHaveBeenCalledTimes(1);

    window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, onExpand);
  });
});
