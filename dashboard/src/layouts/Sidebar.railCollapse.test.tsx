import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LayoutModeProvider } from "../context/LayoutModeContext";
import { LAYOUT_MODE_KEY } from "./layoutModeStorage";
import Sidebar from "./Sidebar";
import seamStyles from "../components/RailSeamHandle.module.less";
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

/**
 * The nav folds from a handle straddling the seam on its right — not from a
 * corner of its own header. These pin the handle to the line that moves and
 * pin the arrow to the state, since a fold control pointing the wrong way is
 * worse than no fold control.
 */
describe("nav rail seam handle", () => {
  beforeEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
  });

  it("hangs off the rail's trailing seam, pointing at the edge it folds to", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    const { container } = renderSidebar({ collapsed: false, onToggle });

    const button = screen.getByRole("button", { name: "收起导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");
    // The accelerator is advertised, not baked into the name.
    expect(button.getAttribute("title")).toMatch(/收起导航栏 \(.+B\)/);

    // Outside the rail (which clips its own width animation), inside its host,
    // so the capsule straddles the divider instead of being cut off by it.
    const rail = container.querySelector<HTMLElement>(`.${styles.navRail}`)!;
    const host = container.querySelector<HTMLElement>(
      `.${styles.navRailHost}`,
    )!;
    const anchor = container.querySelector<HTMLElement>(
      `.${seamStyles.anchor}`,
    )!;
    expect(rail).not.toContainElement(button);
    expect(host).toContainElement(button);
    expect(anchor).toContainElement(button);

    // Expanded, it sits above the centre line so the history rail's own handle
    // (below it) can share this seam when that rail is closed.
    expect(anchor.style.getPropertyValue("--seam-offset")).toBe("-34px");
    expect(anchor).not.toHaveClass(seamStyles.persistent);

    await user.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("stays painted once folded, and points the other way", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    const { container } = renderSidebar({ collapsed: true, onToggle });

    expect(
      screen.queryByRole("button", { name: "收起导航栏" }),
    ).not.toBeInTheDocument();

    const button = screen.getByRole("button", { name: "展开导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");
    // Nothing else in a 56px icon column advertises the way back.
    expect(
      container.querySelector<HTMLElement>(`.${seamStyles.anchor}`),
    ).toHaveClass(seamStyles.persistent);

    await user.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("anchors to the seam in CSS instead of a fixed x", () => {
    const css = readFileSync(
      resolve(__dirname, "../components/RailSeamHandle.module.less"),
      "utf8",
    );
    const anchor = css.match(/\.anchor\s*\{([^}]+)\}/)?.[1];
    // `left: 100%` is what makes the handle follow the column's edge when the
    // column folds; a pixel offset would strand it mid-air.
    expect(anchor).toContain("left: 100%");
    expect(anchor).toContain("calc(50% + var(--seam-offset, 0px))");
    expect(anchor).toContain("translate(-50%, -50%)");
    expect(anchor).toContain("z-index: 40");

    // Quiet at rest, crisp under the pointer — the hover trigger itself.
    const btn = css.match(/\n\.btn\s*\{([^}]+)\}/)?.[1];
    expect(btn).toContain("opacity: 0");
    expect(css).toContain("&:hover {\n    opacity: 1;");
  });

  it("renders one handle in minimal layout too", () => {
    localStorage.setItem(LAYOUT_MODE_KEY, "minimal");
    renderSidebar({ collapsed: false });
    expect(screen.getAllByRole("button", { name: "收起导航栏" })).toHaveLength(
      1,
    );
  });

  it("leaves room for the traffic lights without a second control", () => {
    const { container } = renderSidebar({ collapsed: true });
    const rail = container.querySelector<HTMLElement>(`.${styles.navRail}`)!;
    expect(rail.style.minWidth).toContain(
      "var(--window-controls-inset-start, 0px) + 40px",
    );
  });

  it("keeps the mobile close control in its drawer header", async () => {
    const onToggle = vi.fn();
    renderSidebar({ collapsed: false, isMobile: true, onToggle });
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
 * The nav never folds the history rail. That rail has its own handle on its own
 * seam; the nav growing a second one is what made the corner unreadable.
 */
describe("nav rail keeps to its own panel", () => {
  beforeEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
  });

  it("offers no history-rail toggle", () => {
    renderSidebar({ collapsed: false });
    expect(
      screen.queryByRole("button", { name: /展开对话历史|收起对话历史/ }),
    ).not.toBeInTheDocument();
  });
});
