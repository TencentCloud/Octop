import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  it("opens a dialog with the CLI reset tip when asked", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("login-forgot-password")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByTestId("login-forgot-password-toggle"));

    const dialog = await screen.findByRole("dialog");
    const hint = screen.getByTestId("login-forgot-password");
    expect(dialog).toContainElement(hint);
    expect(hint.textContent).toMatch(/octop user passwd/);
    expect(hint.textContent).toMatch(/--password/);
    expect(hint.textContent).toMatch(/Users|用户/);
    expect(hint.textContent).toMatch(/Linux|终端|Terminal/);

    // antd Segmented radios use pointer-events:none on the input; click the label text.
    await user.click(screen.getByText("Windows"));
    expect(hint.textContent).toMatch(/USERPROFILE/);
    expect(hint.textContent).not.toMatch(/docker exec/);

    await user.click(screen.getByText("Docker"));
    expect(hint.textContent).toMatch(/docker exec/);
  });
});
