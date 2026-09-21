import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ConversationModePicker from "./ConversationModePicker";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("ConversationModePicker", () => {
  it("selects a mode from the menu", async () => {
    const onChange = vi.fn();
    render(
      <ConversationModePicker
        compact
        conversationMode="craft"
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("conversation-mode-picker"));
    const plan = await screen.findByText("chat.conversationMode.plan");
    expect(plan.closest("button")).toHaveTextContent(
      "chat.conversationMode.planHint",
    );
    fireEvent.click(plan);
    expect(onChange).toHaveBeenCalledWith("plan");
  });
});
