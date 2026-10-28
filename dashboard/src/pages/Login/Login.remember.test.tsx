import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../../api/modules/auth", () => ({
  authApi: {
    getAuthStatus: () => Promise.resolve({ setup_required: false }),
    getOauthStatus: () => Promise.resolve({ providers: [] }),
    getLdapStatus: () => Promise.resolve({ enabled: false }),
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
  it("renders checked by default", async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>,
      );
    });

    const checkbox = screen.getByRole("checkbox", {
      name: /login\.remember|记住登录状态|Remember me/,
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

describe("SSO popup completion under a public base", () => {
  const originalLocation = window.location;
  afterEach(() => {
    vi.unstubAllEnvs();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it.each([
    [undefined, "/tools/octop/chat"],
    [
      "/chat/expert/thread?view=history#last",
      "/tools/octop/chat/expert/thread?view=history#last",
    ],
    ["//another.example/chat", "/tools/octop/chat"],
  ])(
    "keeps the opener inside Octop for redirect %s",
    async (redirect, expected) => {
      vi.stubEnv("BASE_URL", "/tools/octop/");
      const replace = vi.fn();
      Object.defineProperty(window, "location", {
        configurable: true,
        value: {
          pathname: "/tools/octop/login",
          origin: "http://localhost:3000",
          replace,
        },
      });
      await act(async () => {
        render(
          <MemoryRouter>
            <LoginPage />
          </MemoryRouter>,
        );
      });
      act(() => {
        window.dispatchEvent(
          new MessageEvent("message", {
            origin: "http://localhost:3000",
            data: { type: "octop-sso", ok: true, redirect },
          }),
        );
      });
      expect(replace).toHaveBeenCalledWith(expected);
    },
  );
});
