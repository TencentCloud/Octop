import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TFunction } from "i18next";
import { describe, expect, it, vi } from "vitest";
import SidebarCollapsedIconNav from "./SidebarCollapsedIconNav";
import styles from "./Sidebar.module.less";
import type { NavItem } from "./sidebarNav";

/**
 * Collapsing the rail throws the row labels away, so each icon has to carry its
 * own name. Without it a screen reader announces "button, button, button" and
 * the visual tooltip is the only thing left to tell them apart.
 */

const labels: Record<string, string> = {
  "nav.chat": "对话",
  "nav.experts": "专家",
};

const t = ((key: string) => labels[key] ?? key) as unknown as TFunction;

const items: NavItem[] = [
  { key: "chat", path: "/chat", icon: <span />, labelKey: "nav.chat" },
  { key: "experts", path: "/experts", icon: <span />, labelKey: "nav.experts" },
];

function renderNav(selectedKey: string, onNavigate = vi.fn()) {
  render(
    <SidebarCollapsedIconNav
      items={items}
      selectedKey={selectedKey}
      onNavigate={onNavigate}
      role="user"
      hasUpdate={false}
      t={t}
    />,
  );
  return onNavigate;
}

describe("collapsed icon nav", () => {
  it("names every icon after its row label", () => {
    renderNav("chat");

    expect(screen.getByRole("button", { name: "对话" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "专家" })).toBeInTheDocument();
  });

  it("marks the current page and only the current page", () => {
    renderNav("experts");

    expect(screen.getByRole("button", { name: "专家" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("button", { name: "对话" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it.each([56, 68, 120])(
    "centers a fixed tile, not a full-bleed stripe, across a %ipx rail",
    (railWidth) => {
      const { container } = render(
        <div style={{ width: railWidth }}>
          <SidebarCollapsedIconNav
            items={items}
            selectedKey="chat"
            onNavigate={vi.fn()}
            role="user"
            hasUpdate={false}
            t={t}
          />
        </div>,
      );
      const stack = container.querySelector(`.${styles.collapsedNav}`);
      expect(stack).not.toBeNull();
      expect(stack?.parentElement).toHaveStyle({ width: `${railWidth}px` });
      for (const name of ["对话", "专家"]) {
        const button = screen.getByRole("button", { name });
        expect(button.classList.contains(styles.collapsedNavBtn)).toBe(true);
        expect(button.parentElement).toBe(stack);
      }
      expect(screen.getByRole("button", { name: "对话" }).className).toContain(
        styles.collapsedNavBtnActive,
      );
      expect(
        screen.getByRole("button", { name: "专家" }).className,
      ).not.toContain(styles.collapsedNavBtnActive);
    },
  );

  it("navigates from an icon", async () => {
    const user = userEvent.setup();
    const onNavigate = renderNav("chat");

    await user.click(screen.getByRole("button", { name: "专家" }));
    expect(onNavigate).toHaveBeenCalledWith("/experts");
  });
});
