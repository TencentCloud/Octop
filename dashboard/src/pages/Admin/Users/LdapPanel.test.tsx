import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { getLdapConfig, putLdapConfig, testLdapConfig, stableT } = vi.hoisted(
  () => ({
    getLdapConfig: vi.fn(),
    putLdapConfig: vi.fn(),
    testLdapConfig: vi.fn(),
    // Identity-stable t: the global auto-mock in src/test/setup.ts creates a
    // fresh t on every useTranslation() call, and LdapPanel's load callback
    // depends on t, which would loop its load effect during tests.
    stableT: (key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? key,
  }),
);

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: stableT }),
}));

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: {
    getLdapConfig,
    putLdapConfig,
    testLdapConfig,
    getOidcConfig: vi.fn(),
    putOidcConfig: vi.fn(),
    testOidcConfig: vi.fn(),
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

import { message } from "@/utils/antdMessage";

import LdapPanel from "./LdapPanel";

const baseConfig = {
  enabled: false,
  display_name: "Corp LDAP",
  server_url: "ldap://directory.example.com",
  start_tls: false,
  verify_tls: true,
  bind_dn: "cn=svc,dc=example,dc=com",
  has_bind_password: true,
  user_base_dn: "ou=people,dc=example,dc=com",
  user_filter: "(uid={username})",
  username_attribute: "uid",
  email_attribute: "mail",
  display_name_attribute: "cn",
  subject_attribute: "entryUUID",
  group_attribute: "memberOf",
  group_search: false,
  group_search_base: "",
  group_member_attribute: "",
  admin_groups: "",
  allowed_groups: "",
  auto_provision: true,
  timeout_seconds: 10,
  warnings: [],
};

describe("<LdapPanel />", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getLdapConfig.mockResolvedValue({ ...baseConfig });
    putLdapConfig.mockImplementation(async (body: Record<string, unknown>) => ({
      ...baseConfig,
      ...body,
      has_bind_password: true,
      warnings: [],
    }));
  });

  it("saves with group search off without crashing on unmounted group fields", async () => {
    const user = userEvent.setup();
    render(<LdapPanel />);

    await waitFor(() => expect(getLdapConfig).toHaveBeenCalledOnce());
    await user.click(
      screen.getByRole("button", { name: "adminSso.ldap.save" }),
    );

    await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
    const body = putLdapConfig.mock.calls[0][0];
    expect(body.group_search).toBe(false);
    // The group inputs never mounted; they must be sent as empty strings
    // instead of throwing "Cannot read properties of undefined (reading
    // 'trim')".
    expect(body.group_search_base).toBe("");
    expect(body.group_member_attribute).toBe("");
    expect(message.error).not.toHaveBeenCalled();
    expect(message.success).toHaveBeenCalledWith("adminSso.ldap.saved");
  });

  it("sends timeout_seconds even when the Advanced section was never expanded", async () => {
    const user = userEvent.setup();
    render(<LdapPanel />);

    await waitFor(() => expect(getLdapConfig).toHaveBeenCalledOnce());
    expect(
      screen.queryByLabelText("adminSso.ldap.timeout"),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "adminSso.ldap.save" }),
    );

    await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
    const body = putLdapConfig.mock.calls[0][0];
    expect(body.timeout_seconds).toBe(10);
    expect(message.error).not.toHaveBeenCalled();
  });

  it("trims and forwards group fields when group search is enabled", async () => {
    const user = userEvent.setup();
    render(<LdapPanel />);

    await waitFor(() => expect(getLdapConfig).toHaveBeenCalledOnce());
    await user.click(
      screen.getByRole("switch", { name: "adminSso.ldap.groupSearch" }),
    );
    await user.type(
      screen.getByLabelText("adminSso.ldap.groupSearchBase"),
      "  ou=groups,dc=example,dc=com  ",
    );
    await user.click(
      screen.getByRole("button", { name: "adminSso.ldap.save" }),
    );

    await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
    const body = putLdapConfig.mock.calls[0][0];
    expect(body.group_search).toBe(true);
    expect(body.group_search_base).toBe("ou=groups,dc=example,dc=com");
    expect(body.group_member_attribute).toBe("");
    expect(message.error).not.toHaveBeenCalled();
  });

  it("keeps the stored bind password when the field is left untouched", async () => {
    const user = userEvent.setup();
    render(<LdapPanel />);

    await waitFor(() => expect(getLdapConfig).toHaveBeenCalledOnce());
    await user.click(
      screen.getByRole("button", { name: "adminSso.ldap.save" }),
    );

    await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
    const body = putLdapConfig.mock.calls[0][0];
    expect(body.bind_password).toBeUndefined();
  });
});
