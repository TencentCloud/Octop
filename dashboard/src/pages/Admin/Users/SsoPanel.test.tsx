import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { getOidcConfig, putOidcConfig, testOidcConfig } = vi.hoisted(() => ({
  getOidcConfig: vi.fn(),
  putOidcConfig: vi.fn(),
  testOidcConfig: vi.fn(),
}));

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: {
    getOidcConfig,
    putOidcConfig,
    testOidcConfig,
    getOauthProvider: vi.fn(),
    putOauthProvider: vi.fn(),
    testOauthProvider: vi.fn(),
    getFeishuConfig: vi.fn(),
    putFeishuConfig: vi.fn(),
    testFeishuConfig: vi.fn(),
  },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

import SsoPanel from "./SsoPanel";

describe("<SsoPanel />", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads the OIDC configuration and displays its callback URL", async () => {
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
    expect(screen.getByText("adminSso.statusEnabled")).toBeInTheDocument();
    expect(screen.getByText("adminSso.oidcKind")).toBeInTheDocument();
    expect(screen.getByText("adminSso.guideTitle")).toBeInTheDocument();
    expect(screen.getByText("adminSso.loginPreview")).toBeInTheDocument();
    expect(
      screen.queryByText("adminSso.oauthFamilyTitle"),
    ).not.toBeInTheDocument();
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
    const preset = screen.getByRole("button", {
      name: "adminSso.presetGoogle",
    });
    /* ★ 只在「请求已发出」之后等待会早于 `loading=false` 的那次重渲染：
       面板此时仍被 `<Spin spinning>` 的模糊层覆盖（`pointer-events: none`），
       全量并发下 `user.click` 会因该 CSS 直接抛错（历史 flake 的根因）。
       ⇒ 这里**只增加等待**（等模糊层清除），不改任何期望值。 */
    await waitFor(() =>
      expect(getComputedStyle(preset).pointerEvents).not.toBe("none"),
    );
    await user.click(preset);
    expect(screen.getByDisplayValue("Google")).toBeInTheDocument();
  });
});
