import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { pluginsApi, type AgentPluginTool } from "../../api/modules/plugins";
import { agentToolsApi } from "../../api/modules/agentTools";
import AgentPluginsPanel from "../../pages/Agent/Personalization/components/AgentPluginsPanel";
import ToolsPanel from "../../pages/Agent/Tools/ToolsPanel";
import { pluginToolNeedsConfig } from "../../utils/pluginToolConfig";

vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});
vi.mock("../../api/modules/plugins", () => ({
  pluginsApi: {
    listAgentPlugins: vi.fn(),
    listAgentTools: vi.fn(),
    patchAgentTools: vi.fn(),
  },
}));
vi.mock("../../api/modules/agentTools", () => ({
  agentToolsApi: { get: vi.fn() },
}));
vi.mock("../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

const tool: AgentPluginTool = {
  plugin_id: "demo",
  name: "echo_prefix",
  enabled: true,
  config_fields: [{ name: "prefix", label: "Prefix", required: true }],
  config: {},
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(pluginsApi.listAgentPlugins).mockResolvedValue({
    plugins: [
      {
        id: "demo",
        name: "Demo",
        loaded: true,
        enabled: true,
        global_enabled: true,
        agent_enabled: true,
        tools: [tool],
      },
    ],
  });
  vi.mocked(pluginsApi.listAgentTools).mockResolvedValue({ tools: [tool] });
  vi.mocked(pluginsApi.patchAgentTools).mockResolvedValue({ status: "ok" });
  vi.mocked(agentToolsApi.get).mockResolvedValue({
    tools: [
      {
        name: tool.name,
        label: tool.name,
        source: "plugin",
        category: "plugin",
        plugin_id: tool.plugin_id,
        enabled: true,
        disableable: true,
      },
    ],
  });
});

describe("plugin configuration discovery", () => {
  it.each(["tools", "plugins"])(
    "configures from the %s page and clears the missing-field badge",
    async (page) => {
      const user = userEvent.setup();
      render(
        page === "tools" ? (
          <ToolsPanel agentId="agent-a" source="plugin" />
        ) : (
          <AgentPluginsPanel agentId="agent-a" />
        ),
      );
      expect(
        await screen.findByText("plugins.needsConfig"),
      ).toBeInTheDocument();
      if (page === "plugins")
        await user.click(
          screen.getByRole("button", { name: "plugins.viewDetails" }),
        );
      await user.click(
        await screen.findByRole("button", { name: "plugins.configure" }),
      );
      await user.type(await screen.findByLabelText("Prefix"), "hello");
      await user.click(screen.getByRole("button", { name: "common.save" }));
      await waitFor(() =>
        expect(pluginsApi.patchAgentTools).toHaveBeenCalledWith("agent-a", {
          demo: { tools: { echo_prefix: { config: { prefix: "hello" } } } },
        }),
      );
      await waitFor(() =>
        expect(
          screen.queryByText("plugins.needsConfig"),
        ).not.toBeInTheDocument(),
      );
    },
  );

  it("validates required fields and starts each tool with its own configuration", async () => {
    const user = userEvent.setup();
    vi.mocked(pluginsApi.listAgentTools).mockResolvedValue({
      tools: [
        { ...tool, config: { prefix: "first", private_option: "keep" } },
        { ...tool, name: "second", config: {} },
      ],
    });
    render(<AgentPluginsPanel agentId="agent-a" />);
    await user.click(
      await screen.findByRole("button", { name: "plugins.viewDetails" }),
    );
    const buttons = await screen.findAllByRole("button", {
      name: "plugins.configure",
    });
    await user.click(buttons[0]);
    expect(await screen.findByLabelText("Prefix")).toHaveValue("first");
    await user.click(screen.getByRole("button", { name: "common.save" }));
    await waitFor(() =>
      expect(pluginsApi.patchAgentTools).toHaveBeenCalledWith("agent-a", {
        demo: {
          tools: {
            echo_prefix: {
              config: { prefix: "first", private_option: "keep" },
            },
          },
        },
      }),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText("Prefix")).not.toBeInTheDocument(),
    );
    vi.mocked(pluginsApi.patchAgentTools).mockClear();
    await user.click(buttons[1]);
    expect(await screen.findByLabelText("Prefix")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "common.save" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Prefix")).toHaveAttribute(
        "aria-invalid",
        "true",
      ),
    );
    expect(pluginsApi.patchAgentTools).not.toHaveBeenCalled();
  });

  it("closes the configuration drawer when the selected agent changes", async () => {
    const user = userEvent.setup();
    const view = render(<ToolsPanel agentId="agent-a" source="plugin" />);
    await user.click(
      await screen.findByRole("button", { name: "plugins.configure" }),
    );
    expect(await screen.findByLabelText("Prefix")).toBeInTheDocument();
    view.rerender(<ToolsPanel agentId="agent-b" source="plugin" />);
    await waitFor(() =>
      expect(screen.queryByLabelText("Prefix")).not.toBeInTheDocument(),
    );
    expect(pluginsApi.patchAgentTools).not.toHaveBeenCalled();
  });
});

describe("configuration availability and save errors", () => {
  it("offers configuration for optional fields but no button for tools without fields", async () => {
    vi.mocked(pluginsApi.listAgentTools).mockResolvedValue({
      tools: [
        { ...tool, config_fields: [{ name: "prefix", required: false }] },
      ],
    });
    const view = render(<ToolsPanel agentId="agent-a" source="plugin" />);
    expect(
      await screen.findByRole("button", { name: "plugins.configure" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("plugins.needsConfig")).not.toBeInTheDocument();
    vi.mocked(pluginsApi.listAgentTools).mockResolvedValue({
      tools: [{ ...tool, config_fields: [] }],
    });
    view.rerender(<ToolsPanel agentId="agent-b" source="plugin" />);
    await screen.findByText("echo_prefix");
    expect(
      screen.queryByRole("button", { name: "plugins.configure" }),
    ).not.toBeInTheDocument();
  });

  it("keeps entered values and the pending badge after a failed save", async () => {
    const user = userEvent.setup();
    vi.mocked(pluginsApi.patchAgentTools).mockRejectedValue(
      new Error("save failed"),
    );
    render(<ToolsPanel agentId="agent-a" source="plugin" />);
    await user.click(
      await screen.findByRole("button", { name: "plugins.configure" }),
    );
    await user.type(await screen.findByLabelText("Prefix"), "retry");
    await user.click(screen.getByRole("button", { name: "common.save" }));
    await waitFor(() =>
      expect(pluginsApi.patchAgentTools).toHaveBeenCalledTimes(1),
    );
    expect(screen.getByLabelText("Prefix")).toHaveValue("retry");
    expect(screen.getByText("plugins.needsConfig")).toBeInTheDocument();
  });
});

describe("required plugin configuration", () => {
  it.each([undefined, null, ""])(
    "marks an empty required value (%s)",
    (value) => {
      expect(
        pluginToolNeedsConfig({ ...tool, config: { prefix: value } }),
      ).toBe(true);
    },
  );
  it.each([0, false, "set"])("accepts an existing value (%s)", (value) => {
    expect(pluginToolNeedsConfig({ ...tool, config: { prefix: value } })).toBe(
      false,
    );
  });
  it("does not require optional or undeclared fields", () => {
    expect(
      pluginToolNeedsConfig({
        ...tool,
        config_fields: [{ name: "prefix", required: false }],
      }),
    ).toBe(false);
    expect(pluginToolNeedsConfig({ ...tool, config_fields: [] })).toBe(false);
  });
});
