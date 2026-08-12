import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import i18n from "../i18n";
import EmojiPicker from "./EmojiPicker";

describe("EmojiPicker", () => {
  it("opens a selectable emoji grid and reports the chosen emoji", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <EmojiPicker value="🤖" onChange={onChange} />
      </I18nextProvider>,
    );

    await user.click(screen.getByRole("button", { name: /emoji/i }));
    const option = await screen.findByRole("option", { name: "⚙️" });
    await user.click(option);

    expect(onChange).toHaveBeenCalledWith("⚙️");
  });
});
