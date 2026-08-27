import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { getOidcConfig, putOidcConfig, testOidcConfig } = vi.hoisted(() => ({
  getOidcConfig: vi.fn(),
  putOidcConfig: vi.fn(),
  testOidcConfig: vi.fn(),
}));

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: { getOidcConfig, putOidcConfig, testOidcConfig },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

import SsoPanel from "./SsoPanel";

describe("<SsoPanel />", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads the provider configuration and displays its callback URL", async () => {
    getOidcConfig.mockResolvedValue({
      enabled: true,
      display_name: "Acme SSO",
      issuer: "https://identity.example.com",
      client_id: "octop",
      scopes: "openid profile email",
      dashboard_origin: "https://octop.example.com",
      has_client_secret: true,
      redirect_uri: "https://octop.example.com/api/auth/oidc/callback",
    });

    render(<SsoPanel />);

    await waitFor(() => expect(getOidcConfig).toHaveBeenCalledOnce());
    expect(screen.getByDisplayValue("Acme SSO")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue(
        "https://octop.example.com/api/auth/oidc/callback",
      ),
    ).toBeInTheDocument();
    // Mocked t() returns the key; interpolation keeps {{name}} unless options used.
    expect(screen.getByText("adminSso.statusEnabled")).toBeInTheDocument();
  });

  it("applies an IdP preset into display name", async () => {
    const user = userEvent.setup();
    getOidcConfig.mockResolvedValue({
      enabled: false,
      display_name: "",
      issuer: "",
      client_id: "",
      scopes: "openid profile email",
      dashboard_origin: null,
      has_client_secret: false,
      redirect_uri: "",
    });

    render(<SsoPanel />);

    await waitFor(() => expect(getOidcConfig).toHaveBeenCalledOnce());
    await user.click(
      screen.getByRole("button", { name: "adminSso.presetGoogle" }),
    );
    expect(screen.getByDisplayValue("Google")).toBeInTheDocument();
  });
});
