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

  it("approves and rejects through the decision callback", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "Allow" }));
    fireEvent.click(await screen.findByText("Allow this tool for this chat"));
    expect(onDecision).toHaveBeenCalledWith([{ type: "approve" }], {
      mode: "allow_tools",
      tools: ["execute"],
    });

    fireEvent.click(screen.getByRole("button", { name: "Allow" }));
    fireEvent.click(await screen.findByText("Allow all for this chat"));
    expect(onDecision).toHaveBeenCalledWith([{ type: "approve" }], {
      mode: "allow_all",
    });

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onDecision).toHaveBeenCalledWith([
      { type: "reject", message: "Rejected by user" },
    ]);
  });

  it("uses plural allow copy when several tools are waiting", async () => {
    render(
      <HitlApprovalCard
        actions={[
          { name: "execute", args: { command: "ls" } },
          { name: "write_file", args: { path: "a.txt" } },
        ]}
        status="pending"
        onDecision={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Allow" }));
    expect(
      await screen.findByText("Allow these tools for this chat"),
    ).toBeInTheDocument();
  });

  it("shows the session policy after approval", () => {
    const { rerender } = render(
      <HitlApprovalCard
        actions={[{ name: "execute", args: { command: "ls" } }]}
        status="approved"
        resolution="allow_all"
      />,
    );
    expect(screen.getByText("Allowed all for this chat")).toBeInTheDocument();

    rerender(
      <HitlApprovalCard
        actions={[{ name: "execute", args: { command: "ls" } }]}
        status="approved"
        resolution="allow_tool"
      />,
    );
    expect(
      screen.getByText("Allowed this tool for this chat"),
    ).toBeInTheDocument();
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
