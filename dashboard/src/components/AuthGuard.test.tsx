import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AuthGuard from "./AuthGuard";

vi.mock("../api/modules/auth", () => ({
  authApi: {
    getAuthStatus: vi.fn(),
    me: vi.fn(),
  },
}));

vi.mock("../api/request", () => ({
  getAuthToken: vi.fn(() => null),
  clearAuthToken: vi.fn(),
}));

vi.mock("../utils/locale", () => ({
  applyUserLocale: vi.fn(() => Promise.resolve()),
}));

import { authApi } from "../api/modules/auth";

describe("AuthGuard offline boot", () => {
  beforeEach(() => {
    vi.mocked(authApi.getAuthStatus).mockReset();
    vi.mocked(authApi.me).mockReset();
  });

  it("shows offline panel instead of the protected shell when setup/status fails", async () => {
    vi.mocked(authApi.getAuthStatus).mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    render(
      <MemoryRouter>
        <AuthGuard>
          <div>protected-shell</div>
        </AuthGuard>
      </MemoryRouter>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert.textContent).toMatch(/errors\.offlineTitle|Cannot reach|无法连接/);
    expect(screen.getByRole("button", { name: /errors\.retry|Retry|重试/ })).toBeInTheDocument();
    expect(screen.queryByText("protected-shell")).not.toBeInTheDocument();
  });
});
