import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LayoutModeProvider } from "../context/LayoutModeContext";
import { useChatSidebarOpen } from "../pages/Chat/hooks/useChatSidebarState";
import edgeStyles from "../components/RailEdgeControl.module.less";
import { LAYOUT_MODE_KEY } from "./layoutModeStorage";
import Sidebar from "./Sidebar";
import styles from "./Sidebar.module.less";

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

function renderSidebar(opts: {
  collapsed: boolean;
  onToggle?: () => void;
  isMobile?: boolean;
}) {
  return render(
    <LayoutModeProvider>
      <MemoryRouter initialEntries={["/chat"]}>
        <Sidebar
          selectedKey="chat"
          collapsed={opts.collapsed}
          onToggle={opts.onToggle ?? (() => undefined)}
          isMobile={opts.isMobile ?? false}
        />
      </MemoryRouter>
    </LayoutModeProvider>,
  );
}

/** The history rail's open flag is a module-level store shared with the page. */
function setHistoryRailOpen(open: boolean) {
  let setter: ((value: boolean) => void) | null = null;
  function Probe() {
    const [, setOpen] = useChatSidebarOpen();
    setter = setOpen as (value: boolean) => void;
    return null;
  }
  const { unmount } = render(<Probe />);
  act(() => setter?.(open));
  unmount();
}

/**
 * Both left columns fold from one shape: a capsule on their seam. The nav used
 * to fold from a `PanelLeftClose` glyph in its top row — a control in a corner
 * that belongs to the window, not to the panel. These pin the seam contract:
 * where the handle lives, what it says, and what it does.
 */
describe("nav rail seam handle", () => {
  beforeEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
    setHistoryRailOpen(true);
  });

  it("collapses from a handle straddling its own seam", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    const { container } = renderSidebar({ collapsed: false, onToggle });

    const button = screen.getByRole("button", { name: "收起导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");
    // The accelerator is advertised, not baked into the name.
    expect(button.getAttribute("title")).toMatch(/收起导航栏 \(.+B\)/);

    // Sits on the seam: outside the rail (which clips its width), inside the host.
    const host = container.querySelector<HTMLElement>(
      `.${styles.navRailHost}`,
    )!;
    expect(host).toContainElement(button);
    expect(container.querySelector(`.${styles.navRail}`)).not.toContainElement(
      button,
    );

    await user.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("keeps the window-controls band as spacing, with no control in it", () => {
    const { container } = renderSidebar({ collapsed: false });
    const band = container.querySelector<HTMLElement>(`.${styles.navChrome}`)!;
    expect(band).toBeInTheDocument();
    expect(band).toBeEmptyDOMElement();

    const css = readFileSync(resolve(__dirname, "Sidebar.module.less"), "utf8");
    const chrome = css.match(/\.navChrome\s*\{([^}]+)\}/)?.[1];
    expect(chrome).toContain("var(--octop-shell-top-band, 58px)");
  });

  it("stays painted while collapsed — it is the only way back", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    renderSidebar({ collapsed: true, onToggle });

    expect(
      screen.queryByRole("button", { name: "收起导航栏" }),
    ).not.toBeInTheDocument();

    const button = screen.getByRole("button", { name: "展开导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");
    expect(button).toHaveClass(edgeStyles.btnPersistent);
    // Alone on its seam when the history rail is open: no second handle, no shift.
    expect(button).not.toHaveClass(edgeStyles.btnTop);

    await user.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("renders one handle in minimal layout too", () => {
    localStorage.setItem(LAYOUT_MODE_KEY, "minimal");
    renderSidebar({ collapsed: false });
    expect(screen.getAllByRole("button", { name: "收起导航栏" })).toHaveLength(
      1,
    );
  });

  it("stacks above the history handle when both share one seam", () => {
    // History rail closed: its handle lands on the nav's divider.
    setHistoryRailOpen(false);
    renderSidebar({ collapsed: false });
    expect(screen.getByRole("button", { name: "收起导航栏" })).toHaveClass(
      edgeStyles.btnTop,
    );
  });

  it("centres on its seam while the history rail owns its own", () => {
    setHistoryRailOpen(true);
    renderSidebar({ collapsed: false });
    expect(screen.getByRole("button", { name: "收起导航栏" })).not.toHaveClass(
      edgeStyles.btnTop,
    );
  });

  it("leaves room for the traffic lights without a second control", () => {
    const { container } = renderSidebar({ collapsed: true });
    const rail = container.querySelector<HTMLElement>(`.${styles.navRail}`)!;
    expect(rail.style.minWidth).toContain(
      "var(--window-controls-inset-start, 0px) + 40px",
    );
    expect(rail).not.toContainElement(
      screen.getByRole("button", { name: "展开导航栏" }),
    );
  });

  it("keeps the mobile close control in its drawer header", async () => {
    const onToggle = vi.fn();
    const { container } = renderSidebar({
      collapsed: false,
      isMobile: true,
      onToggle,
    });
    // No seam to hang a handle on inside the drawer.
    expect(container.querySelector(`.${styles.navRailHost}`)).toBeNull();
    expect(
      screen.queryByRole("button", { name: /收起导航栏|展开导航栏/ }),
    ).not.toBeInTheDocument();

    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "nav.collapseSidebar" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});

/**
 * The nav never folds the history rail. That rail has a handle of its own, and
 * the nav growing a second one here is what made the corner unreadable before.
 */
describe("nav rail keeps to its own panel", () => {
  beforeEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
  });

  it("offers no history-rail toggle", () => {
    const { container } = renderSidebar({ collapsed: false });
    expect(
      screen.queryByRole("button", { name: /展开对话历史|收起对话历史/ }),
    ).not.toBeInTheDocument();
    expect(
      container.querySelector(`.${styles.navRailHost}`),
    ).toBeInTheDocument();
  });
});
