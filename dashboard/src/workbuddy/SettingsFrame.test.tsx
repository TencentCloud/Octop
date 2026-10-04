import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { OctopUser } from "../api/modules/auth";
import SettingsFrame from "./SettingsFrame";
const agent = vi.hoisted(() => ({ id: "agent-a" }));
vi.mock("../context/AgentContext", () => ({
  useAgent: () => ({ activeAgentId: agent.id }),
}));
vi.mock("./AgentSettingsPanel", () => ({
  default: () => <input aria-label="Agent config draft" />,
}));
vi.mock("../components/AgentSelector", () => ({
  default: () => <span>Agent picker</span>,
}));
function Address() {
  return <output>{useLocation().pathname}</output>;
}
describe("WorkBuddy settings", () => {
  it("discards obsolete Agent drafts instead of submitting them to the new Agent", async () => {
    agent.id = "agent-a";
    const panel = (
      <MemoryRouter initialEntries={["/settings/agent"]}>
        <SettingsFrame user={null}>Profile</SettingsFrame>
      </MemoryRouter>
    );
    const { rerender } = render(panel);
    await userEvent.type(
      await screen.findByRole("textbox", { name: "Agent config draft" }),
      "Agent A draft",
    );
    agent.id = "agent-b";
    rerender(
      <MemoryRouter initialEntries={["/settings/agent"]}>
        <SettingsFrame user={null}>Profile</SettingsFrame>
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("textbox", { name: "Agent config draft" }),
    ).toHaveValue("");
  });
  it("keeps settings open and changes the location inside the window", async () => {
    const user = { role: "user", permissions: ["providers"] } as OctopUser;
    render(
      <MemoryRouter initialEntries={["/settings/account"]}>
        <SettingsFrame user={user}>
          <input aria-label="Profile draft" />
        </SettingsFrame>
        <Address />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("button", { name: "nav.security" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "nav.users" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "nav.models" }),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox"), "Unsaved name");
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.appearance" }),
    );
    expect(screen.getByRole("textbox")).toHaveValue("Unsaved name");
    expect(
      screen.getByRole("button", { name: "workbuddy.appearance" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("/settings/appearance")).toBeInTheDocument();
  });
  it("blocks an unauthorized settings deep link", () => {
    render(
      <MemoryRouter initialEntries={["/settings/users"]}>
        <SettingsFrame
          user={{ role: "user", permissions: [] } as unknown as OctopUser}
        >
          Profile
        </SettingsFrame>
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("button", { name: "nav.users" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Profile")).not.toBeVisible();
  });
});
