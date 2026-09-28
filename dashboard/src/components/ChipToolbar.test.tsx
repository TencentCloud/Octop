import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChipButton, ChipToolbar } from "./ChipToolbar";

/** antd keeps a closed popover mounted with an `-hidden` class. */
function popoverHidden(): boolean {
  const el = document.querySelector(".ant-popover");
  if (!el) return true;
  return el.classList.contains("ant-popover-hidden");
}

const icon = <span data-testid="chip-icon" />;

describe("ChipToolbar / ChipButton", () => {
  it("renders the toolbar container, the label and the value summary", () => {
    render(
      <ChipToolbar>
        <ChipButton
          icon={icon}
          label="projects.chipStatus"
          value="projects.taskStatusPlanning"
          ariaLabel="projects.chipStatus"
        />
        <ChipButton
          icon={icon}
          label="projects.chipPriority"
          value={null}
          ariaLabel="projects.chipPriority"
        />
      </ChipToolbar>,
    );

    expect(screen.getByTestId("project-chip-toolbar")).toBeInTheDocument();
    expect(screen.getAllByTestId("chip-icon").length).toBe(2);
    // Non-empty value → `label：value`; empty value → label only.
    expect(
      screen.getByRole("button", { name: "projects.chipStatus" }),
    ).toHaveTextContent("projects.chipStatus：projects.taskStatusPlanning");
    expect(
      screen.getByRole("button", { name: "projects.chipPriority" }),
    ).toHaveTextContent("projects.chipPriority");
    expect(
      screen.getByRole("button", { name: "projects.chipPriority" }),
    ).not.toHaveTextContent("：");
  });

  it("honours a custom testId and accepts className", () => {
    render(
      <ChipToolbar testId="custom-toolbar" className="extra-class">
        <ChipButton icon={icon} label="L" ariaLabel="L" />
      </ChipToolbar>,
    );
    const toolbar = screen.getByTestId("custom-toolbar");
    expect(toolbar).toBeInTheDocument();
    expect(toolbar.className).toContain("extra-class");
  });

  it("exposes aria-label and marks the active chip", () => {
    render(
      <ChipToolbar>
        <ChipButton icon={icon} label="L" ariaLabel="分配给" active />
      </ChipToolbar>,
    );
    const chip = screen.getByRole("button", { name: "分配给" });
    expect(chip).toHaveAttribute("aria-label", "分配给");
    // Active chips get a second (highlight) class.
    expect(chip.className.split(" ").filter(Boolean).length).toBe(2);
  });

  it("does not fire onClick when disabled, and stays focusable via aria-disabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <ChipToolbar>
        <ChipButton
          icon={icon}
          label="projects.chipTags"
          ariaLabel="projects.chipTags"
          disabled
          onClick={onClick}
        >
          <div data-testid="chip-popover-body">never</div>
        </ChipButton>
      </ChipToolbar>,
    );

    const chip = screen.getByRole("button", { name: "projects.chipTags" });
    expect(chip).toHaveAttribute("aria-disabled", "true");
    expect(chip).not.toHaveAttribute("disabled");
    await user.click(chip);
    expect(onClick).not.toHaveBeenCalled();
    // A disabled chip is not a popover trigger either.
    expect(screen.queryByTestId("chip-popover-body")).not.toBeInTheDocument();
    expect(popoverHidden()).toBe(true);
  });

  it("fires onClick when enabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <ChipToolbar>
        <ChipButton
          icon={icon}
          label="projects.chipMore"
          ariaLabel="projects.chipMore"
          onClick={onClick}
        />
      </ChipToolbar>,
    );
    await user.click(screen.getByRole("button", { name: "projects.chipMore" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("opens and closes the Popover on click when it has children", async () => {
    const user = userEvent.setup();
    render(
      <ChipToolbar>
        <ChipButton
          icon={icon}
          label="projects.chipParentTask"
          ariaLabel="projects.chipParentTask"
        >
          <div data-testid="chip-popover-body">picker</div>
        </ChipButton>
      </ChipToolbar>,
    );

    expect(document.querySelector(".ant-popover")).toBeNull();

    const chip = screen.getByRole("button", {
      name: "projects.chipParentTask",
    });
    await user.click(chip);
    expect(await screen.findByTestId("chip-popover-body")).toBeInTheDocument();
    await waitFor(() => expect(popoverHidden()).toBe(false));

    await user.click(chip);
    await waitFor(() => expect(popoverHidden()).toBe(true));
  });
});
