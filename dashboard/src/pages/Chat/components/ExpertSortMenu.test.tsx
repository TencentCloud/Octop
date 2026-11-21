import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ExpertSortMenu from "./ExpertSortMenu";

describe("ExpertSortMenu", () => {
  it("lists the three orders and reports the choice", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ExpertSortMenu mode="recent" onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "排序：最近对话" }));
    expect(
      screen.getByRole("menuitem", { name: "最近创建" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "最早创建" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("menuitem", { name: "最早创建" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("oldest");
  });
});
