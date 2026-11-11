import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ConnectorInstance } from "../../../api/modules/connectors";

const api = vi.hoisted(() => ({ listInstances: vi.fn() }));
const oauth = vi.hoisted(() => ({ run: vi.fn() }));

vi.mock("../../../api/modules/connectors", () => ({ connectorsApi: api }));
vi.mock("@/utils/antdMessage", () => ({
  message: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));
vi.mock("../../Agent/Connectors/connectorOAuth", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../Agent/Connectors/connectorOAuth")
  >()),
  runConnectorOAuth: oauth.run,
}));

import {
  ConnectorAuthAction,
  isConnectorAuthError,
} from "./ConnectorAuthAction";

function instance(overrides: Partial<ConnectorInstance>): ConnectorInstance {
  return {
    instance_id: "i1",
    kind: "custom-mcp",
    display_name: "Docs MCP",
    status: "active",
    mcp_server_name: "docs",
    has_credentials: true,
    shared: false,
    owner_user_id: 1,
    can_manage: true,
    auth_status: "expired",
    created_at: 0,
    updated_at: 0,
    ...overrides,
  };
}

beforeEach(() => {
  api.listInstances.mockReset();
  oauth.run.mockReset();
});

describe("isConnectorAuthError", () => {
  it("recognizes the code or the code prefix kept in history", () => {
    expect(isConnectorAuthError("CONNECTOR_AUTH_REQUIRED", "")).toBe(true);
    expect(
      isConnectorAuthError(undefined, "[CONNECTOR_AUTH_REQUIRED] 需要授权"),
    ).toBe(true);
    expect(isConnectorAuthError("stream_error", "boom")).toBe(false);
  });
});

describe("<ConnectorAuthAction />", () => {
  it("authorizes the connector the turn named and re-sends the turn", async () => {
    api.listInstances.mockResolvedValue([
      instance({ mcp_server_name: "other__1", display_name: "Other" }),
      instance({}),
    ]);
    oauth.run.mockResolvedValue({
      status: "ok",
      result: { kind: "custom-mcp", tokens: {} },
    });
    const onAuthorized = vi.fn();

    render(
      <ConnectorAuthAction
        details={{ connectors: [{ server: "docs" }] }}
        onAuthorized={onAuthorized}
      />,
    );
    const button = await screen.findByRole("button", { name: /Docs MCP/ });
    fireEvent.click(button);

    expect(oauth.run).toHaveBeenCalledWith({
      type: "custom_mcp",
      server_name: "docs",
    });
    await waitFor(() => expect(onAuthorized).toHaveBeenCalledTimes(1));
  });

  it("does not re-send after a cancel", async () => {
    api.listInstances.mockResolvedValue([instance({})]);
    oauth.run.mockResolvedValue({ status: "cancelled" });
    const onAuthorized = vi.fn();

    render(<ConnectorAuthAction onAuthorized={onAuthorized} />);
    fireEvent.click(await screen.findByRole("button", { name: /Docs MCP/ }));

    await waitFor(() => expect(oauth.run).toHaveBeenCalled());
    expect(onAuthorized).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Docs MCP/ })).toBeTruthy();
  });

  it("asks a viewer to contact the owner of a shared MCP server", async () => {
    api.listInstances.mockResolvedValue([instance({ can_manage: false })]);

    render(<ConnectorAuthAction />);

    expect(await screen.findByText(/联系它的所有者/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders nothing once nothing needs authorization", async () => {
    api.listInstances.mockResolvedValue([instance({ auth_status: "ok" })]);

    const { container } = render(<ConnectorAuthAction />);

    await waitFor(() => expect(api.listInstances).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
