import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { OctopUser } from "../api/modules/auth";
import { CurrentUserProvider } from "../hooks/useCurrentUser";
import AvatarDropdown from "./AvatarDropdown";

function buildUser(
  role: OctopUser["role"],
  permissions: string[] = [],
): OctopUser {
  return {
    id: 1,
    username: role,
    role,
    display_name: role === "admin" ? "Admin User" : "Regular User",
    locale: "en",
    permissions,
  };
}

async function openAccountMenu(user: OctopUser) {
  const pointer = userEvent.setup();
  render(
    <MemoryRouter>
      <CurrentUserProvider user={user} setUser={vi.fn()}>
        <AvatarDropdown user={user} placement="sidebar" />
      </CurrentUserProvider>
    </MemoryRouter>,
  );

  await pointer.click(
    screen.getByRole("button", { name: new RegExp(user.display_name!) }),
  );
}

describe("<AvatarDropdown /> update access", () => {
  it("hides Check for updates from users without update permission", async () => {
    await openAccountMenu(buildUser("user"));

    expect(screen.queryByText("account.checkUpdates")).not.toBeInTheDocument();
  });

  it.each([
    ["an admin", buildUser("admin")],
    ["an explicitly authorized user", buildUser("user", ["update"])],
  ])("shows Check for updates to %s", async (_label, user) => {
    await openAccountMenu(user);

    expect(await screen.findByText("account.checkUpdates")).toBeInTheDocument();
  });
});
