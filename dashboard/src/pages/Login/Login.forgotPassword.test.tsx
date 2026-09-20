import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../../api/modules/auth", () => ({
  authApi: {
    getAuthStatus: () => Promise.resolve({ setup_required: false }),
    getOauthStatus: () => Promise.resolve({ providers: [] }),
    getCaptcha: () => Promise.resolve({ provider: "none" }),
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

describe("Login forgot-password hint", () => {
  it("tells locked-out operators how to reset via CLI", () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );
    const hint = screen.getByTestId("login-forgot-password");
    expect(hint.textContent).toMatch(/octop user passwd/);
  });
});
