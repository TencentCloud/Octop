import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PlanReadyCard from "./PlanReadyCard";

describe("PlanReadyCard (#616 P6–P8)", () => {
  it("shows execute and continue actions plus brief preview", () => {
    const onExecute = vi.fn();
    const onContinue = vi.fn();
    render(
      <PlanReadyCard
        brief={
          "## Approved plan\n\nDo it.\n\n1. Write file\n\nExecute this plan now.\n"
        }
        onExecute={onExecute}
        onContinue={onContinue}
      />,
    );
    expect(screen.getByTestId("plan-ready-card")).toBeInTheDocument();
    expect(screen.getByTestId("plan-ready-brief")).toHaveTextContent("Do it.");
    expect(screen.getByTestId("plan-ready-brief")).toHaveTextContent(
      "Write file",
    );
    fireEvent.click(screen.getByTestId("plan-ready-execute"));
    expect(onExecute).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("plan-ready-continue"));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
