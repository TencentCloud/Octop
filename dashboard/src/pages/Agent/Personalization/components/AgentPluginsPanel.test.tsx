/**
 * AgentPluginsPanel.test.tsx — finding where to fill a plugin tool's config (#1422).
 *
 * What we cover:
 *   - toolNeedsConfig: only required fields that are blank count
 *   - a plugin card shows 待配置 while an enabled tool is missing required config
 *   - the detail drawer's config button has a visible label, and opens the form
 *   - disabled tools and fully configured tools show no badge
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

vi.mock("../../../../api/modules/plugins", () => ({
  pluginsApi: {
    listAgentPlugins: vi.fn(),
    listAgentTools: vi.fn(),
    patchAgentPlugins: vi.fn(),
    patchAgentTools: vi.fn(),
  },
}));

import {
  pluginsApi,
  type AgentPlugin,
  type AgentPluginTool,
} from "../../../../api/modules/plugins";
import AgentPluginsPanel, { toolNeedsConfig } from "./AgentPluginsPanel";

const PLUGIN: AgentPlugin = {
  id: "feishu-daily-report",
  name: "飞书日报汇总",
  description: "pull reports",
  kind: "tool",
  group: "tools",
  enabled: true,
  global_enabled: true,
} as AgentPlugin;

function tool(overrides: Partial<AgentPluginTool> = {}): AgentPluginTool {
  return {
    plugin_id: PLUGIN.id,
    name: "feishu_daily_report",
    description: "read reports",
    enabled: true,
    config: {},
    config_fields: [
      { name: "app_id", label: "App ID", type: "text", required: true },
      {
        name: "app_secret",
        label: "App Secret",
        type: "password",
        required: true,
      },
      { name: "timezone", label: "时区", type: "text", required: false },
    ],
    ...overrides,
  } as AgentPluginTool;
}

function mockLoad(tools: AgentPluginTool[], plugins: AgentPlugin[] = [PLUGIN]) {
  vi.mocked(pluginsApi.listAgentPlugins).mockResolvedValue({
    plugins,
  } as never);
  vi.mocked(pluginsApi.listAgentTools).mockResolvedValue({ tools } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("toolNeedsConfig", () => {
  it("flags blank or whitespace required fields only", () => {
    expect(toolNeedsConfig(tool())).toBe(true);
    expect(
      toolNeedsConfig(tool({ config: { app_id: "cli_x", app_secret: "  " } })),
    ).toBe(true);
    expect(
      toolNeedsConfig(tool({ config: { app_id: "cli_x", app_secret: "s" } })),
    ).toBe(false);
  });

  it("ignores tools without required fields", () => {
    expect(toolNeedsConfig(tool({ config_fields: [] }))).toBe(false);
    expect(
      toolNeedsConfig(
        tool({
          config_fields: [{ name: "prefix", type: "text", required: false }],
        }),
      ),
    ).toBe(false);
  });
});

// antd drawers mount through a portal with an open animation; give jsdom room on busy CI.
const SLOW = { timeout: 5000 };

describe("AgentPluginsPanel", () => {
  it("marks the card and tool row, and the labelled button opens the form", async () => {
    mockLoad([tool({ config: { app_id: "cli_x" } })]);
    render(<AgentPluginsPanel agentId="ag1" />);

    const card = (await screen.findByText("飞书日报汇总", {}, SLOW)).closest(
      "article",
    )!;
    expect(within(card).getByText("plugins.needsConfig")).toBeTruthy();

    fireEvent.click(within(card).getByText("plugins.viewDetails"));
    await screen.findByRole("button", { name: /plugins\.configure/ }, SLOW);
    expect(
      screen.getAllByText("plugins.needsConfig").length,
    ).toBeGreaterThanOrEqual(2);

    // Re-query: the drawer re-renders once it settles, replacing the first node.
    fireEvent.click(screen.getByRole("button", { name: /plugins\.configure/ }));
    expect(await screen.findByLabelText("App Secret", {}, SLOW)).toBeTruthy();
  });

  it("shows no badge once required fields are filled", async () => {
    mockLoad([tool({ config: { app_id: "cli_x", app_secret: "s" } })]);
    render(<AgentPluginsPanel agentId="ag1" />);

    await screen.findByText("飞书日报汇总");
    expect(screen.queryByText("plugins.needsConfig")).toBeNull();
  });

  it("does not nag about tools the agent has switched off", async () => {
    mockLoad([tool({ enabled: false })]);
    render(<AgentPluginsPanel agentId="ag1" />);

    await screen.findByText("飞书日报汇总");
    expect(screen.queryByText("plugins.needsConfig")).toBeNull();
  });
});
