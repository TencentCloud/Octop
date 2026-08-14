import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request }));

import { ssoApi } from "./sso";

describe("ssoApi", () => {
  beforeEach(() => {
    request.mockReset();
  });

  it("uses the admin OIDC configuration endpoints", async () => {
    const body = {
      enabled: true,
      display_name: "Acme SSO",
      issuer: "https://identity.example.com",
      client_id: "octop",
      scopes: "openid profile email",
      dashboard_origin: "https://octop.example.com",
    };

    await ssoApi.getOidcConfig();
    await ssoApi.putOidcConfig(body);
    await ssoApi.testOidcConfig();

    expect(request).toHaveBeenNthCalledWith(1, "/auth/oidc/config");
    expect(request).toHaveBeenNthCalledWith(2, "/auth/oidc/config", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    expect(request).toHaveBeenNthCalledWith(3, "/auth/oidc/config/test", {
      method: "POST",
    });
  });
});
