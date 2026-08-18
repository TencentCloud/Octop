import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AskUserQuestionCard from "./AskUserQuestionCard";

describe("AskUserQuestionCard", () => {
  it("keeps the final single choice explicit until Submit", () => {
    const onSubmit = vi.fn();
    render(
      <AskUserQuestionCard
        data={{
          pendingId: "pending-1",
          status: "pending",
          questions: [
            {
              id: "database",
              question: "Which database?",
              options: [{ label: "SQLite" }, { label: "PostgreSQL" }],
            },
          ],
        }}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /SQLite/ }));
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "chat.questions.submit" }),
    );
    expect(onSubmit).toHaveBeenCalledWith("pending-1", [
      { id: "database", selected: ["SQLite"] },
    ]);
  });

  it("advances after a non-final single choice", () => {
    render(
      <AskUserQuestionCard
        data={{
          pendingId: "pending-2",
          status: "pending",
          questions: [
            {
              id: "one",
              question: "First question?",
              options: [{ label: "A" }, { label: "B" }],
            },
            {
              id: "two",
              question: "Second question?",
              options: [],
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /A/ }));
    expect(screen.getByText("Second question?")).toBeInTheDocument();
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });
});
