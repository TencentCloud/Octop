import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OctopUser } from "../api/modules/auth";
import { buildNavSections } from "../layouts/sidebarNav";
import Navigation from "./Navigation";
import SecondaryNavigation from "./SecondaryNavigation";
import { WorkBuddyNavigationProvider } from "./navigationModel";

const state = vi.hoisted(() => ({
  user: {
    id: 1,
    username: "operator",
    role: "user",
    display_name: null,
    locale: "en",
    permissions: ["providers"],
  },
  getPreferences: vi.fn(async () => ({})),
}));
vi.mock("../hooks/useCurrentUser", () => ({
  useCurrentUser: () => state.user,
}));
vi.mock("../hooks/useServerCapabilities", () => ({
  useServerCapabilities: () => ({ mobileEnabled: true }),
}));
vi.mock("../api/modules/preferences", () => ({
  preferencesApi: { get: state.getPreferences },
}));
afterEach(() => {
  state.user.permissions = ["providers"];
});

describe("WorkBuddy navigation hierarchy", () => {
  it("keeps control and management modules out of the primary navigation", async () => {
    const user: OctopUser = { ...state.user, role: "admin" };
    const onNavigate = vi.fn();
    render(
      <MemoryRouter initialEntries={["/home"]}>
        <Navigation
          compact={false}
          sections={buildNavSections(user)}
          onNavigate={onNavigate}
        />
      </MemoryRouter>,
    );
    const primary = screen.getByRole("navigation", {
      name: "workbuddy.workspace",
    });
    expect(within(primary).getAllByRole("link")).toHaveLength(5);
    expect(
      within(primary).queryByText("workbuddy.controlConsole"),
    ).not.toBeInTheDocument();
    expect(within(primary).queryByText("nav.models")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.moreCapabilities" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "workbuddy.controlConsole" }),
    );
    expect(onNavigate).toHaveBeenCalledExactlyOnceWith("/workbench");
  });
  it("allows management by module permission for a non-admin user", async () => {
    render(
      <MemoryRouter initialEntries={["/admin/models"]}>
        <WorkBuddyNavigationProvider>
          <SecondaryNavigation />
        </WorkBuddyNavigationProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(state.getPreferences).toHaveBeenCalled());
    const management = screen.getByRole("complementary", {
      name: "workbuddy.systemManagement",
    });
    expect(
      within(management).getByRole("link", { name: "nav.models" }),
    ).toHaveAttribute("href", "/admin/models");
    expect(
      within(management).queryByRole("link", { name: "nav.users" }),
    ).not.toBeInTheDocument();
    expect(within(management).getAllByRole("link")).toHaveLength(1);
  });
  it("does not add a second market navigation column", () => {
    render(
      <MemoryRouter initialEntries={["/experts"]}>
        <WorkBuddyNavigationProvider>
          <SecondaryNavigation />
        </WorkBuddyNavigationProvider>
      </MemoryRouter>,
    );
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
