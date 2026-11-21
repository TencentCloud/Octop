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
  it("uses the LDAP directory endpoints", async () => {
    const body = {
      enabled: true,
      display_name: "Corp Directory",
      server_url: "ldap://directory.example.org",
      start_tls: true,
      verify_tls: false,
      bind_dn: "uid=svc,dc=example,dc=org",
      bind_password: "secret",
      user_base_dn: "dc=example,dc=org",
      user_filter: "(uid={username})",
      username_attribute: "uid",
      email_attribute: "mail",
      display_name_attribute: "givenName",
      subject_attribute: "entryUUID",
      group_attribute: "memberOf",
      group_search: false,
      group_search_base: "",
      group_member_attribute: "member",
      admin_groups: "admin",
      allowed_groups: "staff",
      auto_provision: true,
      timeout_seconds: 10,
    };

    await ssoApi.getLdapConfig();
    await ssoApi.putLdapConfig(body);
    await ssoApi.testLdapConfig();

    expect(request).toHaveBeenNthCalledWith(1, "/auth/ldap/config");
    expect(request).toHaveBeenNthCalledWith(2, "/auth/ldap/config", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    expect(request).toHaveBeenNthCalledWith(3, "/auth/ldap/config/test", {
      method: "POST",
    });
  });
});
