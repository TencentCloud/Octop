import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PlanReadyCard from "./PlanReadyCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { path?: string }) =>
      key === "chat.conversationMode.planReadyBody"
        ? `saved ${opts?.path ?? ""}`
        : key,
  }),
}));

describe("PlanReadyCard", () => {
  it("renders the plan path and both actions", () => {
    const onExecute = vi.fn();
    const onKeepEditing = vi.fn();
    render(
      <PlanReadyCard
        path="plans/add-ask-plan-modes.md"
        onExecute={onExecute}
        onKeepEditing={onKeepEditing}
      />,
    );
    expect(screen.getByTestId("plan-ready-card")).toHaveTextContent(
      "plans/add-ask-plan-modes.md",
    );
    fireEvent.click(screen.getByText("chat.conversationMode.execute"));
    fireEvent.click(screen.getByText("chat.conversationMode.keepEditing"));
    expect(onExecute).toHaveBeenCalledTimes(1);
    expect(onKeepEditing).toHaveBeenCalledTimes(1);
  });
});
