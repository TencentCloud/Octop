import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { LdapConfig } from "../../../api/modules/sso";

const { getLdapConfig, putLdapConfig, t } = vi.hoisted(() => ({
  getLdapConfig: vi.fn(),
  putLdapConfig: vi.fn(),
  t: (key: string) => key,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t,
    i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
  }),
}));

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: {
    getLdapConfig,
    putLdapConfig,
    testLdapConfig: vi.fn(),
  },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

import LdapPanel from "./LdapPanel";

const config: LdapConfig = {
  enabled: false,
  display_name: "Directory",
  server_url: "ldaps://directory.example.com",
  start_tls: false,
  verify_tls: true,
  bind_dn: "",
  has_bind_password: true,
  user_base_dn: "ou=people,dc=example,dc=com",
  user_filter: "(uid={username})",
  username_attribute: "uid",
  email_attribute: "mail",
  display_name_attribute: "cn",
  subject_attribute: "",
  group_attribute: "memberOf",
  group_search: false,
  group_search_base: "ou=groups,dc=example,dc=com",
  group_member_attribute: "uniqueMember",
  admin_groups: "",
  allowed_groups: "",
  auto_provision: false,
  timeout_seconds: 27,
  warnings: [],
};

describe("<LdapPanel /> saving", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getLdapConfig.mockResolvedValue(config);
    putLdapConfig.mockResolvedValue(config);
  });

  it("saves hidden group settings when group search is off", async () => {
    const user = userEvent.setup();
    render(<LdapPanel />);
    await screen.findByDisplayValue(config.server_url);

    fireEvent.change(screen.getByLabelText("adminSso.ldap.displayName"), {
      target: { value: "Updated" },
    });
    await user.click(
      screen.getByRole("button", { name: "adminSso.ldap.save" }),
    );

    await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
    expect(putLdapConfig.mock.calls[0][0]).toMatchObject({
      display_name: "Updated",
      group_search: false,
      group_search_base: config.group_search_base,
      group_member_attribute: config.group_member_attribute,
      timeout_seconds: 27,
      admin_groups: "",
      allowed_groups: "",
    });
    expect(putLdapConfig.mock.calls[0][0]).not.toHaveProperty("bind_password");
  });

  it("keeps an edited group base after group search is turned off", async () => {
    const user = userEvent.setup();
    getLdapConfig.mockResolvedValue({ ...config, group_search: true });
    render(<LdapPanel />);
    await screen.findByDisplayValue(config.server_url);

    fireEvent.change(screen.getByLabelText("adminSso.ldap.groupSearchBase"), {
      target: { value: "ou=new,dc=example,dc=com" },
    });
    await user.click(document.getElementById("group_search") as HTMLElement);
    expect(
      screen.queryByLabelText("adminSso.ldap.groupSearchBase"),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "adminSso.ldap.save" }),
    );

    await waitFor(() => expect(putLdapConfig).toHaveBeenCalledOnce());
    expect(putLdapConfig.mock.calls[0][0]).toMatchObject({
      group_search: false,
      group_search_base: "ou=new,dc=example,dc=com",
      group_member_attribute: "uniqueMember",
      timeout_seconds: 27,
    });
  });
});
