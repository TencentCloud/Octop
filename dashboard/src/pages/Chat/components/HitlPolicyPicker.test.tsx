import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HitlPolicyPicker from "./HitlPolicyPicker";

describe("HitlPolicyPicker", () => {
  it("stays visible while asking every time", () => {
    render(<HitlPolicyPicker policy={{ mode: "ask" }} onChange={vi.fn()} />);
    expect(screen.getByTestId("hitl-policy-picker")).toBeInTheDocument();
  });

  it("shows the current bypass and can reset to ask", async () => {
    const onChange = vi.fn();
    render(
      <HitlPolicyPicker policy={{ mode: "allow_all" }} onChange={onChange} />,
    );
    fireEvent.click(screen.getByTestId("hitl-policy-picker"));
    expect(
      document.querySelectorAll(".ant-popover svg").length,
    ).toBeGreaterThan(0);
    fireEvent.click(await screen.findByText("chat.hitl.policy.ask"));
    expect(onChange).toHaveBeenCalledWith({ mode: "ask" });
  });

  it("can remove one allowed tool without closing the menu", async () => {
    const onChange = vi.fn();
    render(
      <HitlPolicyPicker
        policy={{ mode: "allow_tools", tools: ["execute", "write_file"] }}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("hitl-policy-picker"));
    const removeButtons = await screen.findAllByRole("button", {
      name: "chat.hitl.policy.removeTool",
    });
    fireEvent.click(removeButtons[0]);
    expect(onChange).toHaveBeenCalledWith({
      mode: "allow_tools",
      tools: ["write_file"],
    });
    expect(document.querySelector(".ant-popover")).toBeInTheDocument();
  });
});
