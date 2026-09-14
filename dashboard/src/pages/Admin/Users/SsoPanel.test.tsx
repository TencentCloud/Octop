import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { getOidcConfig, putOidcConfig, testOidcConfig, getOauthProvider } =
  vi.hoisted(() => ({
    getOidcConfig: vi.fn(),
    putOidcConfig: vi.fn(),
    testOidcConfig: vi.fn(),
    getOauthProvider: vi.fn(),
  }));

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: {
    getOidcConfig,
    putOidcConfig,
    testOidcConfig,
    getOauthProvider,
    putOauthProvider: vi.fn(),
    testOauthProvider: vi.fn(),
    getFeishuConfig: () => getOauthProvider("feishu"),
    putFeishuConfig: vi.fn(),
    testFeishuConfig: vi.fn(),
  },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

import SsoPanel from "./SsoPanel";

async function expandOidc(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByText("adminSso.oidcTitle"));
}

describe("<SsoPanel />", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOauthProvider.mockResolvedValue({
      kind: "feishu",
      enabled: false,
      display_name: "",
      client_id: "",
      has_client_secret: false,
      redirect_uri: "https://octop.example.com/api/auth/oauth/callback",
      extra: { region: "feishu" },
    });
  });

  it("loads the provider configuration and displays its callback URL", async () => {
    const user = userEvent.setup();
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
    expect(screen.getByText("adminSso.oauthFamilyTitle")).toBeInTheDocument();
    expect(screen.getByText("adminSso.feishuTitle")).toBeInTheDocument();
    expect(screen.getByText("adminSso.dingtalkTitle")).toBeInTheDocument();
    expect(screen.getByText("adminSso.wecomTitle")).toBeInTheDocument();
    await waitFor(() =>
      expect(getOauthProvider).toHaveBeenCalledWith("feishu"),
    );

    await expandOidc(user);
    expect(screen.getByDisplayValue("Acme SSO")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue(
        "https://octop.example.com/api/auth/oidc/callback",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("adminSso.statusEnabled")).toBeInTheDocument();
    expect(screen.getByText("adminSso.oidcTitle")).toBeInTheDocument();
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
    await expandOidc(user);
    await user.click(
      screen.getByRole("button", { name: "adminSso.presetGoogle" }),
    );
    expect(screen.getByDisplayValue("Google")).toBeInTheDocument();
  });
});
