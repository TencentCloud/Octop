import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import BusinessDetailDialog from "./BusinessDetailDialog";
import { MarketDetailContext } from "../workbuddy/MarketDetailContext";

const variant = vi.hoisted(() => ({ workbuddy: true }));
vi.mock("../workbuddy/variant", () => ({
  get WORKBUDDY_UI() {
    return variant.workbuddy;
  },
}));

describe("business detail display frame", () => {
  it("renders market skills inline and returns without losing editor callbacks", async () => {
    variant.workbuddy = true;
    const close = vi.fn();
    const save = vi.fn();
    render(
      <MarketDetailContext.Provider value>
        <BusinessDetailDialog
          open
          kind="skill"
          title="Skill details"
          onClose={close}
          footer={<button onClick={save}>Save skill</button>}
        >
          <input aria-label="Skill content" />
        </BusinessDetailDialog>
      </MarketDetailContext.Provider>,
    );
    await userEvent.type(screen.getByRole("textbox"), "Real skill content");
    expect(document.querySelector(".wb-market-detail")).toBeInTheDocument();
    expect(document.querySelector(".ant-modal")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Save skill" }));
    expect(save).toHaveBeenCalledOnce();
    expect(screen.getByRole("textbox")).toHaveValue("Real skill content");
    await userEvent.click(screen.getByRole("button", { name: "common.back" }));
    expect(close).toHaveBeenCalledOnce();
  });
  it("retains form input and calls the existing save callback", async () => {
    variant.workbuddy = true;
    const save = vi.fn();
    const props = {
      open: true,
      title: "Edit agent",
      width: 640,
      onClose: vi.fn(),
      footer: <button onClick={save}>Save agent</button>,
      children: <input aria-label="Agent name" />,
    };
    const { rerender } = render(<BusinessDetailDialog {...props} />);
    await userEvent.type(screen.getByRole("textbox"), "Research agent");
    rerender(<BusinessDetailDialog {...props} title="Save changes" />);
    expect(screen.getByRole("textbox")).toHaveValue("Research agent");
    expect(document.querySelector(".ant-modal")).toHaveStyle({
      width: "520px",
    });
    await userEvent.click(screen.getByRole("button", { name: "Save agent" }));
    expect(save).toHaveBeenCalledOnce();
  });
  it("closes with the existing cancel callback without submitting", async () => {
    variant.workbuddy = true;
    const close = vi.fn(),
      save = vi.fn();
    render(
      <BusinessDetailDialog
        open
        title="Edit automation"
        onClose={close}
        footer={<button onClick={save}>Save</button>}
      >
        <input aria-label="Task name" />
      </BusinessDetailDialog>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(close).toHaveBeenCalledOnce();
    expect(save).not.toHaveBeenCalled();
  });
  it("keeps the original drawer width in the rollback display", () => {
    variant.workbuddy = false;
    render(
      <BusinessDetailDialog open title="Legacy editor" width={640}>
        <input aria-label="Agent name" />
      </BusinessDetailDialog>,
    );
    expect(document.querySelector(".ant-drawer-content-wrapper")).toHaveStyle({
      width: "640px",
    });
    expect(document.querySelector(".ant-modal")).toBeNull();
  });
});
