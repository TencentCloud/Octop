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

describe("Login remember-me checkbox", () => {
  it("renders checked by default", () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    const checkbox = screen.getByRole("checkbox", {
      name: /login\.remember|在这台设备上保持登录|Stay signed in on this device/,
    });
    expect(checkbox).toBeChecked();
    expect(
      screen.getByPlaceholderText(
        /login\.username|用户名或邮箱|username or email/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        /login\.usernameHint|可用安装时设置|set during setup/i,
      ),
    ).not.toBeInTheDocument();
  });
});
