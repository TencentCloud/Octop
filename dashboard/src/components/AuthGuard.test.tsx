import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { useEffect } from "react";
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
import { getAuthToken } from "../api/request";

// The shell mounts asynchronously; under load (this repo's CI box runs several
// suites at once, load average >14) the *default* findBy/waitFor window (1000ms)
// is not enough. Measured: 4/10 failures on the current tree with the default
// window, both with and without the current `setup.ts` (baseline arm: 2/10), so
// the window — not the setup — was the variable. Aligned with vitest's own
// `test.timeout` default (5000ms) so the wait can never outlive the test.
const SHELL_WAIT_MS = 5000;

describe("AuthGuard offline boot", () => {
  beforeEach(() => {
    vi.mocked(authApi.getAuthStatus).mockReset();
    vi.mocked(authApi.me).mockReset();
    vi.mocked(getAuthToken).mockReset();
    vi.mocked(getAuthToken).mockReturnValue(null);
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
    expect(alert.textContent).toMatch(
      /errors\.offlineTitle|Cannot reach|无法连接/,
    );
    expect(
      screen.getByRole("button", { name: /errors\.retry|Retry|重试/ }),
    ).toBeInTheDocument();
    expect(screen.queryByText("protected-shell")).not.toBeInTheDocument();
  });

  it("keeps the authenticated shell mounted across in-app navigations", async () => {
    vi.mocked(getAuthToken).mockReturnValue("tok");
    vi.mocked(authApi.getAuthStatus).mockResolvedValue({
      setup_required: false,
      has_admin: true,
    } as never);
    vi.mocked(authApi.me).mockResolvedValue({
      user_id: 1,
      username: "admin",
      role: "admin",
      locale: "zh",
    } as never);

    function NavProbe() {
      const navigate = useNavigate();
      useEffect(() => {
        navigate("/b");
      }, [navigate]);
      return <div>protected-shell</div>;
    }

    render(
      <MemoryRouter initialEntries={["/a"]}>
        <AuthGuard>
          <Routes>
            <Route path="/a" element={<NavProbe />} />
            <Route path="/b" element={<div>protected-shell</div>} />
          </Routes>
        </AuthGuard>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        "protected-shell",
        {},
        { timeout: SHELL_WAIT_MS },
      ),
    ).toBeInTheDocument();
    await waitFor(
      () => {
        expect(authApi.getAuthStatus).toHaveBeenCalledTimes(1);
      },
      { timeout: SHELL_WAIT_MS },
    );
    // Give route-driven navigate identity churn a tick; gate must not re-run.
    await waitFor(
      () => {
        expect(screen.getByText("protected-shell")).toBeInTheDocument();
      },
      { timeout: SHELL_WAIT_MS },
    );
    expect(authApi.getAuthStatus).toHaveBeenCalledTimes(1);
    expect(authApi.me).toHaveBeenCalledTimes(1);
  });

  it("retries auth from the offline panel without leaving a blank shell", async () => {
    vi.mocked(authApi.getAuthStatus)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue({
        setup_required: false,
        has_admin: true,
      } as never);
    vi.mocked(getAuthToken).mockReturnValue("tok");
    vi.mocked(authApi.me).mockResolvedValue({
      user_id: 1,
      username: "admin",
      role: "admin",
      locale: "zh",
    } as never);

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AuthGuard>
          <div>protected-shell</div>
        </AuthGuard>
      </MemoryRouter>,
    );

    const retry = await screen.findByRole("button", {
      name: /errors\.retry|Retry|重试/,
    });
    await user.click(retry);
    expect(await screen.findByText("protected-shell")).toBeInTheDocument();
  });
});
