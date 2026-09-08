import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AskQuestionCard from "./AskQuestionCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const questions = [
  {
    header: "Framework",
    question: "Which framework?",
    options: [{ label: "React" }, { label: "Vue" }],
  },
  {
    header: "Database",
    question: "Which databases?",
    multi_select: true,
    options: [{ label: "PostgreSQL" }, { label: "Redis" }],
  },
];

describe("AskQuestionCard", () => {
  it("shows exactly one question at a time", () => {
    render(
      <AskQuestionCard
        questions={questions}
        status="pending"
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByText("Which framework?")).toBeInTheDocument();
    expect(screen.queryByText("Which databases?")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /React/ }));

    expect(screen.queryByText("Which framework?")).not.toBeInTheDocument();
    expect(screen.getByText("Which databases?")).toBeInTheDocument();
  });

  it("collects all answers before submitting once", () => {
    const onSubmit = vi.fn();
    render(
      <AskQuestionCard
        questions={questions}
        status="pending"
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /React/ }));
    fireEvent.click(screen.getByRole("button", { name: /PostgreSQL/ }));
    fireEvent.click(screen.getByRole("button", { name: "chat.ask.review" }));

    expect(screen.getByText("Which framework?")).toBeInTheDocument();
    expect(screen.getByText("Which databases?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "chat.ask.submit" }));
    expect(onSubmit).toHaveBeenCalledWith(
      "Framework: React\nDatabase: PostgreSQL",
    );
  });

  it("renders open-ended questions as a text field directly", () => {
    render(
      <AskQuestionCard
        questions={[{ question: "Anything else?" }]}
        status="pending"
        onSubmit={vi.fn()}
      />,
    );

    expect(
      screen.getByPlaceholderText("chat.ask.freeTextPlaceholder"),
    ).toBeInTheDocument();
    expect(screen.queryByText("chat.ask.other")).not.toBeInTheDocument();
  });

  it("closes the card without answering", () => {
    const onSubmit = vi.fn();
    const onDismiss = vi.fn();
    render(
      <AskQuestionCard
        questions={questions}
        status="pending"
        onSubmit={onSubmit}
        onDismiss={onDismiss}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "chat.ask.dismiss" }));

    expect(onDismiss).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("collapses an answered question set in message history", () => {
    const { container } = render(
      <AskQuestionCard questions={questions} status="approved" />,
    );

    const details = container.querySelector("details");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText("chat.ask.answeredSummary")).toBeInTheDocument();
    expect(screen.queryByText("Which framework?")).not.toBeVisible();

    fireEvent.click(container.querySelector("summary")!);
    expect(details).toHaveAttribute("open");
    expect(screen.getByText("Which framework?")).toBeVisible();
  });
});
