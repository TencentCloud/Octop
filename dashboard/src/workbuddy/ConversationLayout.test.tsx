import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ConversationLayout from "./ConversationLayout";
import Recommendations from "./Recommendations";

vi.mock("./variant", () => ({ WORKBUDDY_UI: true }));
const cards = Array.from({ length: 9 }, (_, index) => ({
  title: `Task ${index}`,
  description: `Description ${index}`,
  prompt: `Prompt ${index}`,
  color: "",
}));

describe("production welcome layout", () => {
  it("preserves the composer DOM and draft when welcome becomes a conversation", async () => {
    const onPromptClick = vi.fn();
    const { rerender } = render(
      <ConversationLayout welcome cards={cards} onPromptClick={onPromptClick}>
        <input className="wb-composer" aria-label="Draft" />
      </ConversationLayout>,
    );
    const composer = screen.getByRole("textbox", { name: "Draft" });
    await userEvent.type(composer, "Unsent draft");
    rerender(
      <ConversationLayout
        welcome={false}
        cards={cards}
        onPromptClick={onPromptClick}
      >
        <input className="wb-composer" aria-label="Draft" />
      </ConversationLayout>,
    );
    expect(screen.getByRole("textbox", { name: "Draft" })).toBe(composer);
    expect(composer).toHaveValue("Unsent draft");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
  it("paginates configured recommendations without dropping later prompts or sending them", async () => {
    const onPromptClick = vi.fn();
    render(<Recommendations cards={cards} onPromptClick={onPromptClick} />);
    expect(
      screen.queryByRole("button", { name: "Task 4" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "workbuddy.previousRecommendations" }),
    ).toBeDisabled();
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.nextRecommendations" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /Task 7$/ }));
    expect(onPromptClick).toHaveBeenCalledExactlyOnceWith("Prompt 7", {
      prefill: true,
    });
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.nextRecommendations" }),
    );
    expect(screen.getByRole("button", { name: /Task 8$/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "workbuddy.nextRecommendations" }),
    ).toBeDisabled();
  });
});
