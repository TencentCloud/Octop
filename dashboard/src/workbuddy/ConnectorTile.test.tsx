import { App } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type {
  ConnectorCatalogEntry,
  ConnectorInstance,
} from "../api/modules/connectors";
import { ConnectorCard } from "../pages/Agent/Connectors/ConnectorCard";
import { ConnectorInstanceCard } from "../pages/Agent/Connectors/ConnectorInstanceCard";

const { patchInstance } = vi.hoisted(() => ({
  patchInstance: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("./variant", () => ({ WORKBUDDY_UI: true }));
vi.mock("../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1 }),
}));
vi.mock("../api/modules/connectors", () => ({
  connectorsApi: { patchInstance },
}));
const entry: ConnectorCatalogEntry = {
  kind: "custom",
  name: "Octop connector",
  description: "Actual catalog entry",
  auth_kind: "api_key",
  doc_url: "",
  icon: "",
  color: "#333",
  phase: "available",
  mcp_mode: "gateway",
  category: "productivity",
};
const instance: ConnectorInstance = {
  instance_id: "connector-1",
  kind: "custom",
  display_name: "Shared connector",
  status: "active",
  mcp_server_name: "server",
  has_credentials: true,
  shared: true,
  owner_user_id: 2,
  can_manage: false,
  created_at: 0,
  updated_at: 0,
};

describe("WorkBuddy connector bindings", () => {
  it("opens the existing configuration callback once from the original add button", async () => {
    const onConfigure = vi.fn();
    render(<ConnectorCard entry={entry} onConfigure={onConfigure} />);
    await userEvent.click(screen.getByRole("button", { name: "点击连接" }));
    expect(onConfigure).toHaveBeenCalledExactlyOnceWith(entry, null);
  });
  it("does not configure a coming-soon catalog entry or a read-only shared instance", async () => {
    const onConfigure = vi.fn(),
      onEdit = vi.fn();
    render(
      <App>
        <ConnectorCard
          entry={{ ...entry, phase: "coming_soon" }}
          onConfigure={onConfigure}
        />
        <ConnectorInstanceCard
          instance={instance}
          catalogEntry={entry}
          onEdit={onEdit}
          onChanged={vi.fn()}
        />
      </App>,
    );
    expect(screen.getByRole("button", { name: "点击连接" })).toBeDisabled();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "common.delete" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByText(instance.display_name));
    expect(onEdit).not.toHaveBeenCalled();
    expect(onConfigure).not.toHaveBeenCalled();
  });
  it("uses the real instance id for a toggle and refreshes without opening edit", async () => {
    const onEdit = vi.fn(),
      onChanged = vi.fn();
    patchInstance.mockClear();
    render(
      <App>
        <ConnectorInstanceCard
          instance={{ ...instance, can_manage: true, owner_user_id: 1 }}
          catalogEntry={entry}
          onEdit={onEdit}
          onChanged={onChanged}
        />
      </App>,
    );
    await userEvent.click(screen.getByRole("switch"));
    await waitFor(() =>
      expect(patchInstance).toHaveBeenCalledExactlyOnceWith("connector-1", {
        status: "disabled",
      }),
    );
    expect(onChanged).toHaveBeenCalledOnce();
    expect(onEdit).not.toHaveBeenCalled();
  });
});
