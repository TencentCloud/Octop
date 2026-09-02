import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DesktopWindowControls from "./DesktopWindowControls";

const { emitDesktopWindowAction } = vi.hoisted(() => ({
  emitDesktopWindowAction: vi.fn(),
}));

vi.mock("../../utils/desktopChrome", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../utils/desktopChrome")
  >();
  return { ...actual, emitDesktopWindowAction };
});

describe("DesktopWindowControls", () => {
  it("renders traffic lights with close on the far right", async () => {
    const user = userEvent.setup();
    render(<DesktopWindowControls chrome="mac" />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    expect(buttons[0]).toHaveAccessibleName(/maximize/i);
    expect(buttons[1]).toHaveAccessibleName(/minimize/i);
    expect(buttons[2]).toHaveAccessibleName(/close/i);

    await user.click(buttons[2]);
    expect(emitDesktopWindowAction).toHaveBeenCalledWith("close");
  });

  it("renders Windows caption buttons in min / max / close order", async () => {
    const user = userEvent.setup();
    render(<DesktopWindowControls chrome="windows" />);

    const buttons = screen.getAllByRole("button");
    expect(buttons[0]).toHaveAccessibleName(/minimize/i);
    expect(buttons[1]).toHaveAccessibleName(/maximize/i);
    expect(buttons[2]).toHaveAccessibleName(/close/i);

    await user.click(buttons[0]);
    expect(emitDesktopWindowAction).toHaveBeenCalledWith("minimise");
  });
});
