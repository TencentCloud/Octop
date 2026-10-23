import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { Dispatch, SetStateAction } from "react";
import type { OctopUser } from "../../../api/modules/auth";
import { CurrentUserProvider } from "../../../hooks/useCurrentUser";

const { getOauthProvider, putOauthProvider, testOauthProvider } = vi.hoisted(
  () => ({
    getOauthProvider: vi.fn(),
    putOauthProvider: vi.fn(),
    testOauthProvider: vi.fn(),
  }),
);

vi.mock("../../../api/modules/sso", () => ({
  ssoApi: {
    getOauthProvider,
    putOauthProvider,
    testOauthProvider,
    getOidcConfig: vi.fn(),
    putOidcConfig: vi.fn(),
    testOidcConfig: vi.fn(),
    getFeishuConfig: vi.fn(),
    putFeishuConfig: vi.fn(),
    testFeishuConfig: vi.fn(),
  },
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({ activeAgent: null }),
}));

vi.mock("../../../hooks/useIsMobile", () => ({
  useIsMobile: () => false,
}));

vi.mock("./UsersListPanel", () => ({
  default: () => <div>users-list</div>,
}));

import AdminUsersPage from "./index";

/** 测试用管理员：role=admin 会绕过页签权限，8 个 tab 全部显示 */
const adminUser: OctopUser = {
  id: 1,
  username: "admin",
  role: "admin",
  display_name: "Admin",
  locale: "zh",
};

/** 未启用的空外部系统配置 */
const emptyOauth = {
  kind: "external",
  enabled: false,
  display_name: "",
  client_id: "",
  has_client_secret: false,
  extra: {},
};

function renderUsers(path: string) {
  const setUser = vi.fn() as Dispatch<SetStateAction<OctopUser | null>>;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CurrentUserProvider user={adminUser} setUser={setUser}>
        <AdminUsersPage />
      </CurrentUserProvider>
    </MemoryRouter>,
  );
}

describe("AdminUsersPage external tab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOauthProvider.mockResolvedValue(emptyOauth);
  });

  it("shows all 8 tabs and the external panel from ?tab=external", async () => {
    renderUsers("/admin/users?tab=external");

    expect(screen.getAllByRole("tab")).toHaveLength(8);
    expect(
      screen.getByRole("tab", { name: /外部系统登录|adminUsers.tabExternal/ }),
    ).toBeInTheDocument();
    expect(document.querySelector('[data-tab="external"]')).toBeTruthy();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", {
          name: /adminSso.externalTitle|外部系统登录/,
        }),
      ).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(
        screen.getByText(
          /adminSso.externalExchangeTitle|POST \/api\/auth\/external\/exchange/,
        ),
      ).toBeInTheDocument();
    });
  });

  it("keeps the external tab visible on the default users URL", () => {
    renderUsers("/admin/users");

    expect(screen.getAllByRole("tab")).toHaveLength(8);
    expect(
      screen.getByRole("tab", { name: /外部系统登录|adminUsers.tabExternal/ }),
    ).toBeInTheDocument();
    expect(document.querySelector('[data-tab="external"]')).toBeTruthy();
  });
});
