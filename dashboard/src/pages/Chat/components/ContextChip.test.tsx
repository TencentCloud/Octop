import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ContextChip from "./ContextChip";

it("keeps connector configuration and removal as separate actions", () => {
  const open = vi.fn();
  const remove = vi.fn();
  render(
    <ContextChip
      variant="connector"
      icon={null}
      label="OpenDesign"
      openLabel="Configure OpenDesign"
      onOpen={open}
      onRemove={remove}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Configure OpenDesign" }));
  expect(open).toHaveBeenCalledOnce();
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "OpenDesign", exact: true }),
  );
  expect(remove).toHaveBeenCalledOnce();
  expect(open).toHaveBeenCalledOnce();
});
