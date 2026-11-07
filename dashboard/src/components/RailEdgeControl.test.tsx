import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RailEdgeControl from "./RailEdgeControl";
import styles from "./RailEdgeControl.module.less";

describe("RailEdgeControl", () => {
  it("points left while expanded and reveals on the edge", () => {
    render(
      <RailEdgeControl
        expanded
        onToggle={() => undefined}
        label="收起导航栏"
      />,
    );

    const button = screen.getByRole("button", { name: "收起导航栏" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button.querySelector("svg")?.getAttribute("class")).toContain(
      "chevron-left",
    );
    expect(button.closest(`.${styles.edge}`)).toHaveClass(styles.edgeEnd);
  });

  it("puts the resize grip on the upper stretch of the line", () => {
    const onResizeStart = vi.fn();
    render(
      <RailEdgeControl
        expanded
        onToggle={() => undefined}
        onResizeStart={onResizeStart}
        resizeLabel="调整侧栏宽度"
      />,
    );

    const grip = screen.getByRole("separator", { name: "调整侧栏宽度" });
    expect(grip).toHaveClass(styles.resizeGrip);
    fireEvent.pointerDown(grip, { button: 0, pointerId: 1, clientX: 20 });
    expect(onResizeStart).toHaveBeenCalledTimes(1);
  });
});
