import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import i18n from "../../../i18n";

const { getOidcConfig, putOidcConfig, testOidcConfig } = vi.hoisted(() => ({
  getOidcConfig: vi.fn(),
  putOidcConfig: vi.fn(),
  testOidcConfig: vi.fn(),
}));

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: { getOidcConfig, putOidcConfig, testOidcConfig },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn() },
}));

import SsoPanel from "./SsoPanel";

describe("<SsoPanel />", () => {
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

    render(
      <I18nextProvider i18n={i18n}>
        <SsoPanel />
      </I18nextProvider>,
    );

    await waitFor(() => expect(getOidcConfig).toHaveBeenCalledOnce());
    expect(screen.getByDisplayValue("Acme SSO")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue(
        "https://octop.example.com/api/auth/oidc/callback",
      ),
    ).toBeInTheDocument();
  });
});
