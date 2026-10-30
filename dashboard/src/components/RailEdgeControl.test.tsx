import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RailEdgeControl from "./RailEdgeControl";

describe("RailEdgeControl", () => {
  it("starts a resize when the edge is dragged", () => {
    const onResizeStart = vi.fn();
    const { container } = render(
      <RailEdgeControl
        expanded
        onToggle={() => undefined}
        onResizeStart={onResizeStart}
      />,
    );

    fireEvent.pointerDown(container.firstChild as HTMLElement);

    expect(onResizeStart).toHaveBeenCalledTimes(1);
  });

  it("leaves the collapse button to collapse", () => {
    const onResizeStart = vi.fn();
    const onToggle = vi.fn();
    render(
      <RailEdgeControl
        expanded
        onToggle={onToggle}
        onResizeStart={onResizeStart}
      />,
    );

    const button = screen.getByRole("button");
    fireEvent.pointerDown(button);
    fireEvent.click(button);

    expect(onResizeStart).not.toHaveBeenCalled();
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("does nothing on drag when the panel is not resizable", () => {
    const { container } = render(
      <RailEdgeControl expanded onToggle={() => undefined} />,
    );
    const edge = container.firstChild as HTMLElement;

    expect(() => fireEvent.pointerDown(edge)).not.toThrow();
    expect(edge.className).not.toMatch(/edgeResizable/);
  });
});
