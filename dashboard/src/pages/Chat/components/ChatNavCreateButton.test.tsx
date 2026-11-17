import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ChatNavCreateButton } from "./ChatNavScopeTabs";
import type { ChatNavScope } from "../utils/chatNavScope";

function renderButton(scope: ChatNavScope, onCreate = () => undefined) {
  render(<ChatNavCreateButton scope={scope} onCreate={onCreate} />);
}

describe("ChatNavCreateButton", () => {
  it("opens the new-expert drawer from the experts tab", async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();
    renderButton("experts", onCreate);
    await user.click(screen.getByRole("button", { name: "创建专家" }));
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it("opens the team drawer from the teams tab", async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();
    renderButton("teams", onCreate);
    await user.click(screen.getByRole("button", { name: "创建团队" }));
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it("opens the cloud drawer from the cloud tab", async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn();
    renderButton("cloud", onCreate);
    await user.click(screen.getByRole("button", { name: "添加云端" }));
    expect(onCreate).toHaveBeenCalledOnce();
  });
});
