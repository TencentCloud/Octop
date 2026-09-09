import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PlanReadyCard from "./PlanReadyCard";

describe("PlanReadyCard (#616 P6–P8)", () => {
  it("shows execute and continue actions", () => {
    const onExecute = vi.fn();
    const onContinue = vi.fn();
    render(
      <PlanReadyCard
        brief="## Approved plan\n\nDo it.\n"
        onExecute={onExecute}
        onContinue={onContinue}
      />,
    );
    expect(screen.getByTestId("plan-ready-card")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("plan-ready-execute"));
    expect(onExecute).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("plan-ready-continue"));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
