import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import type {
  ConnectorCatalogEntry,
  ConnectorInstance,
} from "../../../api/modules/connectors";

const { catalog, instances } = vi.hoisted(() => {
  const catalog: ConnectorCatalogEntry[] = [
    {
      kind: "notion",
      name: "Notion",
      description: "",
      auth_kind: "oauth",
      doc_url: "",
      icon: "",
      color: "#000",
      phase: "available",
      mcp_mode: "gateway",
      category: "knowledge",
    },
    {
      kind: "amap",
      name: "Amap",
      description: "",
      auth_kind: "api_key",
      doc_url: "",
      icon: "",
      color: "#000",
      phase: "available",
      mcp_mode: "gateway",
      category: "travel",
    },
    {
      kind: "docs",
      name: "Docs",
      description: "",
      auth_kind: "api_key",
      doc_url: "",
      icon: "",
      color: "#000",
      phase: "available",
      mcp_mode: "gateway",
      category: "office",
    },
  ];
  const instances: ConnectorInstance[] = [
    {
      instance_id: "notes",
      kind: "notion",
      display_name: "My Notion",
      status: "ready",
      mcp_server_name: "notion",
      has_credentials: true,
      shared: false,
      owner_user_id: 1,
      can_manage: true,
      created_at: 0,
      updated_at: 0,
    },
    {
      instance_id: "maps",
      kind: "amap",
      display_name: "My Maps",
      status: "ready",
      mcp_server_name: "amap",
      has_credentials: true,
      shared: false,
      owner_user_id: 1,
      can_manage: true,
      created_at: 0,
      updated_at: 0,
    },
  ];
  return { catalog, instances };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
  }),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock("./useConnectors", () => ({
  useConnectorInstances: () => ({
    catalog,
    instances,
    loading: false,
    refresh: vi.fn(),
  }),
}));

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({
    id: 1,
    username: "admin",
    role: "admin",
    display_name: "Admin",
    locale: "zh",
  }),
}));

vi.mock("./CustomMcpTab", () => ({
  CustomMcpTab: () => <div>custom-tab</div>,
}));

import ConnectorsPage from "./index";

function renderPage() {
  return render(
    <MemoryRouter>
      <ConnectorsPage />
    </MemoryRouter>,
  );
}

describe("ConnectorsPage category pills", () => {
  it("filters enabled instances and the built-in catalog", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByText("My Notion")).toBeInTheDocument();
    expect(screen.getByText("My Maps")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "connectors.category.knowledge" }),
    );
    expect(screen.getByText("My Notion")).toBeInTheDocument();
    expect(screen.queryByText("My Maps")).not.toBeInTheDocument();
    expect(
      screen.queryByText("connectors.categoryEmpty"),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "connectors.category.office" }),
    );
    expect(screen.queryByText("My Notion")).not.toBeInTheDocument();
    expect(screen.getByText("connectors.categoryEmpty")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "connectors.categoryAll" }),
    );
    expect(screen.getByText("My Notion")).toBeInTheDocument();
    expect(screen.getByText("My Maps")).toBeInTheDocument();

    await user.click(
      screen.getByRole("tab", { name: "connectors.tabBuiltin" }),
    );
    expect(screen.getByText("Notion")).toBeInTheDocument();
    expect(screen.getByText("Amap")).toBeInTheDocument();
    expect(screen.getByText("Docs")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "connectors.category.travel" }),
    );
    expect(screen.queryByText("Notion")).not.toBeInTheDocument();
    expect(screen.queryByText("Docs")).not.toBeInTheDocument();
    expect(screen.getByText("Amap")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "connectors.tabCustom" }));
    expect(
      screen.queryByRole("button", { name: "connectors.categoryAll" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("custom-tab")).toBeInTheDocument();
  });
});
