import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const { getLdapConfig, putLdapConfig } = vi.hoisted(() => ({
  getLdapConfig: vi.fn(),
  putLdapConfig: vi.fn(),
}));

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: { getLdapConfig, putLdapConfig, testLdapConfig: vi.fn() },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});

import LdapPanel from "./LdapPanel";

const config = {
  enabled: false,
  display_name: "Directory",
  server_url: "ldaps://directory.example.com",
  start_tls: false,
  verify_tls: true,
  bind_dn: "cn=service,dc=example,dc=com",
  user_base_dn: "dc=example,dc=com",
  user_filter: "(uid={username})",
  username_attribute: "uid",
  email_attribute: "mail",
  display_name_attribute: "cn",
  subject_attribute: "",
  group_attribute: "memberOf",
  group_search: true,
  group_search_base: "ou=groups,dc=example,dc=com",
  group_member_attribute: "member",
  admin_groups: "",
  allowed_groups: "",
  auto_provision: false,
  timeout_seconds: 10,
  has_bind_password: true,
  warnings: [],
};

describe("LDAP bind password", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getLdapConfig.mockResolvedValue(config);
    putLdapConfig.mockResolvedValue(config);
  });

  it.each([" secret ", "\tsecret\t", "   ", "secret"])(
    "saves the exact password %j",
    async (password) => {
      render(<LdapPanel />);
      await screen.findByDisplayValue(config.bind_dn);
      fireEvent.change(screen.getByLabelText(/adminSso.ldap.bindPassword/), {
        target: { value: password },
      });
      fireEvent.click(
        screen.getByRole("button", { name: "adminSso.ldap.save" }),
      );

      await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
      expect(putLdapConfig.mock.calls[0][0].bind_password).toBe(password);
    },
  );

  it("omits an untouched password so the stored secret is retained", async () => {
    render(<LdapPanel />);
    await screen.findByDisplayValue(config.bind_dn);
    fireEvent.click(screen.getByRole("button", { name: "adminSso.ldap.save" }));

    await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
    expect(putLdapConfig.mock.calls[0][0]).not.toHaveProperty("bind_password");
  });
});
