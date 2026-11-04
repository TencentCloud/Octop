import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const passkeyStatus = vi.hoisted(() => ({ passwordless_login: false }));

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../../api/modules/auth", () => ({
  authApi: {
    getAuthStatus: () => Promise.resolve({ setup_required: false }),
    getOauthStatus: () => Promise.resolve({ providers: [] }),
    getCaptcha: () => Promise.resolve({ provider: "none" }),
    getLdapStatus: () => Promise.resolve({ enabled: false, display_name: "" }),
    getPasskeyLoginStatus: () => Promise.resolve({ ...passkeyStatus }),
  },
}));

vi.mock("../../utils/locale", () => ({
  applyGuestLocale: () => Promise.resolve(),
  applyUserLocale: () => Promise.resolve(),
}));

vi.mock("./CaptchaField", () => ({
  default: () => null,
}));

import LoginPage from "./index";

const signIn = /login\.passkeySignIn|使用通行密钥登录|Sign in with a passkey/;
const httpsHint =
  /login\.passkeyHttpsRequired|通行密钥需要安全连接|Passkeys require a secure connection/;

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("Login passkey button", () => {
  it("stays hidden until passwordless login is enabled", async () => {
    passkeyStatus.passwordless_login = false;
    renderLogin();
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(screen.queryByText(signIn)).not.toBeInTheDocument();
    expect(screen.queryByText(httpsHint)).not.toBeInTheDocument();
  });

  it("offers passkey sign-in after the setting is turned on", async () => {
    passkeyStatus.passwordless_login = true;
    renderLogin();
    await waitFor(() => {
      const visible =
        screen.queryByText(signIn) ?? screen.queryByText(httpsHint);
      expect(visible).not.toBeNull();
    });
  });
});
