import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PluginDetails from "./PluginDetails";

vi.mock("./variant", () => ({ WORKBUDDY_UI: true }));

function PluginList() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <input aria-label="Filter plugins" />
      <button onClick={() => setOpen(true)}>Plugin details</button>
      <PluginDetails
        open={open}
        title="Configured plugin"
        onClose={() => setOpen(false)}
      >
        <p>Actual enabled state</p>
      </PluginDetails>
    </>
  );
}

describe("source plugin details navigation", () => {
  it("returns to the same list controller, preserving filters and keyboard focus", async () => {
    render(<PluginList />);
    await userEvent.type(screen.getByRole("textbox"), "calendar");
    const opener = screen.getByRole("button", { name: "Plugin details" });
    await userEvent.click(opener);
    const back = screen.getByRole("button", { name: "common.back" });
    expect(back).toHaveFocus();
    await userEvent.click(back);
    expect(screen.queryByText("Actual enabled state")).toBeNull();
    expect(screen.getByRole("textbox")).toHaveValue("calendar");
    expect(opener).toHaveFocus();
  });
});
