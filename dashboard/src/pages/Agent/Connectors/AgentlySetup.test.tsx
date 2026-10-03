import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import {
  connectorsApi,
  type ConnectorCatalogEntry,
  type ConnectorInstance,
} from "../../../api/modules/connectors";
import { useConnectorInstances } from "./useConnectors";
import ConnectorsPage from "./index";

vi.mock("./useConnectors");
vi.mock("../../../layouts/PageShell", () => ({
  default: {
    Tabbed: ({
      tabBar,
      children,
    }: {
      tabBar: ReactNode;
      children: ReactNode;
    }) => (
      <>
        {tabBar}
        {children}
      </>
    ),
  },
}));

afterEach(() => vi.restoreAllMocks());

it("saves an empty-credential mailbox instance and keeps its authorization drawer open", async () => {
  const getComputedStyle = window.getComputedStyle.bind(window);
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    getComputedStyle(element),
  );
  const entry: ConnectorCatalogEntry = {
    kind: "agently-cli",
    name: "Agent Mail",
    description: "An independent agent mailbox",
    auth_kind: "custom_fields",
    doc_url: "https://example.com/docs",
    icon: "agently-cli",
    color: "#1677ff",
    phase: "available",
    mcp_mode: "gateway",
    category: "office",
    credential_fields: [],
  };
  const instance: ConnectorInstance = {
    instance_id: "saved-mail",
    kind: entry.kind,
    display_name: entry.name,
    description: entry.description,
    status: "active",
    mcp_server_name: "saved-mail",
    has_credentials: false,
    shared: false,
    owner_user_id: 1,
    can_manage: true,
    created_at: 0,
    updated_at: 0,
  };
  vi.mocked(useConnectorInstances).mockReturnValue({
    catalog: [entry],
    instances: [],
    loading: false,
    refresh: vi.fn().mockResolvedValue(undefined),
  });
  vi.spyOn(connectorsApi, "authInfo").mockResolvedValue({
    authorize_url: null,
    login_url: null,
    guide_url: null,
    manual_url: null,
    auth_hint: null,
  });
  vi.spyOn(connectorsApi, "cliStatus").mockResolvedValue({
    ok: true,
    installed: true,
    kind: "agently-cli",
    binary: "agently-cli",
    npm_package: "@tencent-qqmail/agently-cli",
    install_command: "npm install -g @tencent-qqmail/agently-cli",
    doc_url: "",
  });
  const create = vi
    .spyOn(connectorsApi, "createInstance")
    .mockResolvedValue(instance);
  vi.spyOn(connectorsApi, "getInstance").mockResolvedValue({
    ...instance,
    config: {},
    credentials_preview: {},
  });
  const auth = vi.spyOn(connectorsApi, "agentlyAuth").mockResolvedValue({
    status: "idle",
    verification_url: null,
    user_code: null,
    expires_at: null,
    error: null,
  });
  render(
    <MemoryRouter>
      <ConnectorsPage />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("tab", { name: "connectors.tabBuiltin" }));
  fireEvent.click(screen.getByText("Agent Mail"));
  expect(await screen.findByRole("dialog")).toHaveTextContent(
    "创建 Agent Mail 连接器",
  );
  expect(screen.getByRole("button", { name: "探测" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() =>
    expect(create).toHaveBeenCalledWith({
      kind: "agently-cli",
      display_name: "Agent Mail",
      description: entry.description,
      credentials: {},
      default_open: false,
      shared: false,
    }),
  );
  expect(await screen.findByText("尚未授权此邮箱实例")).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toHaveTextContent(
    "编辑 Agent Mail 连接器",
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "登录授权" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "登录授权" }));
  await waitFor(() => expect(auth).toHaveBeenCalledWith("saved-mail", "start"));
  expect(create).toHaveBeenCalledTimes(1);
});
