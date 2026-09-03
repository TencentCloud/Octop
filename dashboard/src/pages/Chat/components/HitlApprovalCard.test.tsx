import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HitlApprovalCard from "./HitlApprovalCard";

describe("HitlApprovalCard", () => {
  it("does not dump raw JSON arguments", () => {
    render(
      <HitlApprovalCard
        actions={[
          {
            name: "browser_use",
            args: { action: "dom_tree", level: "interactive" },
          },
        ]}
        status="pending"
        onDecision={vi.fn()}
      />,
    );

    expect(
      screen.getByText("Read the interactive structure of the current page"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/"action"/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\{\s*"action"/)).not.toBeInTheDocument();
    expect(document.querySelector("svg")).toBeTruthy();
  });

  it("approves and rejects through the decision callback", () => {
    const onDecision = vi.fn();
    render(
      <HitlApprovalCard
        actions={[{ name: "execute", args: { command: "ls" } }]}
        status="pending"
        onDecision={onDecision}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onDecision).toHaveBeenCalledWith([{ type: "approve" }]);

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onDecision).toHaveBeenCalledWith([
      { type: "reject", message: "Rejected by user" },
    ]);
  });

  it("does not treat a pending card without a callback as rejected", () => {
    render(
      <HitlApprovalCard
        actions={[{ name: "execute", args: { command: "ls" } }]}
        status="pending"
      />,
    );

    expect(screen.queryByText("Rejected")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
