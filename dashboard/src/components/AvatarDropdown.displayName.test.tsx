import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "zh" },
  }),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("../hooks/useUserRole", () => ({
  useUserRole: () => "user",
}));

vi.mock("../hooks/useIsMobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("../context/LayoutModeContext", () => ({
  useLayoutMode: () => ({
    layoutMode: "classic",
    setLayoutMode: vi.fn(),
  }),
}));

vi.mock("../api/modules/auth", () => ({
  authApi: {
    me: () => Promise.resolve({ id: 1, username: "ada", has_password: true }),
    mfaStatus: () =>
      Promise.resolve({
        totp_verified: false,
        passkeys: [],
        recovery_remaining: 0,
        is_last_factor: false,
        can_enroll: true,
        has_password: true,
        sso_linked: false,
      }),
    getOauthStatus: () => Promise.resolve({ providers: [] }),
    updateProfile: vi.fn(),
    logout: vi.fn(),
  },
}));

vi.mock("../api/modules/preferences", () => ({
  preferencesApi: { setLocale: vi.fn() },
}));

vi.mock("./ThemeSwitcher", () => ({ default: () => null }));
vi.mock("./PaletteSwitcher", () => ({ default: () => null }));

vi.mock("../pages/Admin/Users/ProfileAvatar", () => ({
  ProfileAvatar: () => <span data-testid="profile-avatar" />,
  ProfileAvatarPicker: () => <div data-testid="avatar-picker" />,
}));

import AvatarDropdown from "./AvatarDropdown";

const user = {
  id: 1,
  username: "ada",
  role: "user",
  display_name: "Ada",
  locale: "zh",
};

async function openSettings() {
  const view = userEvent.setup();
  render(<AvatarDropdown user={user} placement="sidebar" />);
  await view.click(screen.getByRole("button", { name: /Ada/ }));
  await view.click(screen.getByRole("button", { name: "account.settings" }));
  return view;
}

describe("AvatarDropdown personal settings", () => {
  it("puts save and cancel in the drawer footer", async () => {
    await openSettings();

    const cancel = await screen.findByRole("button", { name: "common.cancel" });
    const save = screen.getByRole("button", { name: "common.save" });
    const footer = cancel.closest(".ant-drawer-footer");
    expect(footer).toContainElement(save);
    expect(
      screen.queryByRole("button", { name: "account.saveDisplayName" }),
    ).not.toBeInTheDocument();
  });

  it("shows display name, login name, and role on one line without a duplicate avatar", async () => {
    await openSettings();

    const identity = await waitFor(() => {
      const handle = screen.getByText("@ada");
      const row = handle.parentElement;
      expect(row).toBeTruthy();
      return row as HTMLElement;
    });

    expect(identity.textContent).toMatch(
      /Ada[\s\S]*@ada[\s\S]*account\.roleUser/,
    );
    expect(identity.querySelector("[data-testid='profile-avatar']")).toBeNull();
    expect(screen.getByTestId("avatar-picker")).toBeInTheDocument();
  });

  it("opens account security with the password form in one drawer", async () => {
    const view = userEvent.setup();
    render(<AvatarDropdown user={user} placement="sidebar" />);

    await view.click(screen.getByRole("button", { name: /Ada/ }));
    expect(
      screen.queryByRole("button", { name: "account.changePassword" }),
    ).not.toBeInTheDocument();
    await view.click(screen.getByRole("button", { name: "account.security" }));

    expect(
      await screen.findByText("account.currentPassword"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "account.changePassword" }),
    ).toBeInTheDocument();
    expect(
      document.querySelector(".ant-drawer-right, .octop-drawer-right"),
    ).toBeTruthy();
  });
});
