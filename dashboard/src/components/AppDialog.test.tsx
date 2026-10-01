import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppDialog } from "./AppDialog";

/**
 * A11Y-5 regression guard: a surface that declares `aria-modal="true"` must
 * behave modally for the keyboard too.
 *
 * The hand-rolled overlays this replaces announced modality to assistive tech
 * while leaving focus on the trigger behind them, letting Tab walk into the
 * inert page and making Escape a no-op.
 */
describe("AppDialog", () => {
  const renderDialog = (
    props: Partial<React.ComponentProps<typeof AppDialog>> = {},
  ) =>
    render(
      <AppDialog open ariaLabel="Test dialog" {...props}>
        <button>first</button>
        <button>last</button>
      </AppDialog>,
    );

  it("renders nothing when closed", () => {
    render(
      <AppDialog open={false} onClose={() => {}} ariaLabel="Closed">
        <button>inside</button>
      </AppDialog>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("moves focus into the dialog on open", () => {
    renderDialog();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // First focusable control, not the trigger behind the overlay.
    expect(screen.getByRole("button", { name: "first" })).toHaveFocus();
  });

  it("exposes an accessible name and modal semantics", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-label", "Test dialog");
  });

  it("dismisses on Escape when dismissable", async () => {
    const onClose = vi.fn();
    renderDialog({ onClose });

    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores Escape when not dismissable (e.g. mid-restart)", async () => {
    const onClose = vi.fn();
    renderDialog({ onClose, dismissable: false });

    await userEvent.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("supports role=alertdialog for interrupting dialogs", () => {
    renderDialog({ role: "alertdialog" });
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("traps Tab: focus stays inside the dialog", async () => {
    renderDialog();
    const first = screen.getByRole("button", { name: "first" });
    const last = screen.getByRole("button", { name: "last" });

    // Tab forward off the last control wraps back to the first.
    last.focus();
    await userEvent.tab();
    expect(first).toHaveFocus();

    // Shift+Tab from the first wraps to the last.
    await userEvent.tab({ shift: true });
    expect(last).toHaveFocus();
  });

  it("restores focus to the trigger on close", async () => {
    const trigger = document.createElement("button");
    trigger.textContent = "open";
    document.body.appendChild(trigger);
    trigger.focus();
    expect(trigger).toHaveFocus();

    const { rerender } = render(
      <AppDialog open ariaLabel="Test dialog">
        <button>inside</button>
      </AppDialog>,
    );
    expect(screen.getByRole("button", { name: "inside" })).toHaveFocus();

    rerender(<AppDialog open={false} ariaLabel="Test dialog" />);
    expect(trigger).toHaveFocus();

    trigger.remove();
  });
});
