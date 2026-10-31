import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import RailSeamHandle, { SEAM_HANDLE_STEP } from "./RailSeamHandle";
import styles from "./RailSeamHandle.module.less";

/**
 * The handle is the seam's own control: shape, arrow and offset are its whole
 * contract. Placement is CSS (`left: 100%` of the host), so what is asserted
 * here is the state machine and the arrow that has to follow it.
 */
describe("RailSeamHandle", () => {
  it("points left while the panel is open, and folds on click", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <RailSeamHandle
        open
        onToggle={onToggle}
        label="收起导航栏"
        offsetY={-34}
      />,
    );

    const button = screen.getByRole("button", { name: "收起导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button.getAttribute("title")).toBe("收起导航栏");
    expect(button.querySelector("svg")?.getAttribute("class")).toContain(
      "chevron-left",
    );
    expect(button.closest(`.${styles.anchor}`)).not.toHaveClass(
      styles.persistent,
    );

    await user.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("points right and stays painted once the panel is folded", () => {
    render(
      <RailSeamHandle
        open={false}
        onToggle={() => undefined}
        label="展开导航栏"
        hint="展开导航栏 (⌘B)"
        shortcut="Meta+B"
        persistent
      />,
    );

    const button = screen.getByRole("button", { name: "展开导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    // The accelerator lives in the tooltip, never in the accessible name.
    expect(button.getAttribute("title")).toBe("展开导航栏 (⌘B)");
    expect(button).toHaveAttribute("aria-keyshortcuts", "Meta+B");
    expect(button.querySelector("svg")?.getAttribute("class")).toContain(
      "chevron-right",
    );
    expect(button.closest(`.${styles.anchor}`)).toHaveClass(styles.persistent);
  });

  it("carries its offset as a custom property, not as a re-render", () => {
    const { container } = render(
      <RailSeamHandle
        open
        onToggle={() => undefined}
        offsetY={SEAM_HANDLE_STEP}
      />,
    );
    const anchor = container.querySelector<HTMLElement>(`.${styles.anchor}`)!;
    expect(anchor.style.getPropertyValue("--seam-offset")).toBe("34px");
    expect(anchor.style.top).toBe("");
  });

  it("falls back to a generic label when the caller has none", () => {
    render(<RailSeamHandle open onToggle={() => undefined} />);
    expect(
      screen.getByRole("button", { name: "收起面板" }),
    ).toBeInTheDocument();
  });
});
