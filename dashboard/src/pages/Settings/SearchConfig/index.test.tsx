import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { App, ConfigProvider } from "antd";
import zh from "../../../locales/zh.json";
import type {
  CustomSearchConfig,
  CustomSearchProvider,
} from "../../../api/modules/search";

vi.mock("react-i18next", async () => {
  const { default: locale } = await import("../../../locales/zh.json");
  const t = (key: string, options?: Record<string, unknown>) => {
    let value: unknown = locale;
    for (const part of key.split(".")) {
      value = (value as Record<string, unknown>)?.[part];
    }
    const text = typeof value === "string" ? value : key;
    return text.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
      options && name in options ? String(options[name]) : match,
    );
  };
  return { useTranslation: () => ({ t }) };
});

vi.mock("../../../api/modules/env", () => ({
  envsApi: {
    listEnvs: vi.fn(),
    batchSaveEnvs: vi.fn(),
    deleteEnv: vi.fn(),
  },
}));

vi.mock("../../../api/modules/search", () => ({
  searchApi: {
    getCustom: vi.fn(),
    saveCustom: vi.fn(),
    testCustom: vi.fn(),
  },
}));

vi.mock("../../../api", () => ({ default: { testSearch: vi.fn() } }));

import { envsApi } from "../../../api/modules/env";
import { searchApi } from "../../../api/modules/search";
import api from "../../../api";
import SearchConfigPage from "./index";

const envApi = vi.mocked(envsApi, true);
const customApi = vi.mocked(searchApi, true);
const setupApi = vi.mocked(api, true);
const copy = zh.advancedSettings.search.custom;
let configuredPresetIds: string[] | undefined;

const provider: CustomSearchProvider = {
  id: "custom-1",
  name: "My search",
  url: "https://search.example.com/search",
  method: "GET",
  headers: { Authorization: "Bearer {api_key}" },
  params: { q: "{query}", format: "json" },
  body: { query: "{query}", max_results: "{max_results}" },
  results_path: "results",
  title_path: "title",
  url_path: "url",
  content_path: "content",
  api_key_set: true,
};

function envResp(keys: string[]) {
  return keys.map((key, i) => ({ key, value: `v${i}` })) as never;
}

function mount(config?: CustomSearchConfig, envKeys: string[] = []) {
  if (config) customApi.getCustom.mockResolvedValue(config);
  configuredPresetIds = config?.configured_preset_ids;
  envApi.listEnvs.mockResolvedValue(envResp(envKeys));
  return render(
    <ConfigProvider button={{ autoInsertSpace: false }}>
      <App>
        <SearchConfigPage />
      </App>
    </ConfigProvider>,
  );
}

async function openAdd() {
  fireEvent.click(await screen.findByRole("button", { name: copy.add }));
  fireEvent.change(screen.getByLabelText(copy.name), {
    target: { value: "New engine" },
  });
  fireEvent.change(screen.getByLabelText(copy.url), {
    target: { value: "https://new.example.com/search" },
  });
}

async function openEdit() {
  const card = await screen.findByRole("article", { name: provider.name });
  fireEvent.click(within(card).getByRole("button", { name: zh.common.edit }));
}

beforeEach(() => {
  vi.clearAllMocks();
  configuredPresetIds = undefined;
  const getComputedStyle = window.getComputedStyle;
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    getComputedStyle(element),
  );
  customApi.getCustom.mockResolvedValue({
    providers: [],
    active_provider_id: null,
  });
  customApi.saveCustom.mockImplementation(async (config) => {
    const saved = {
      ...config,
      configured_preset_ids: configuredPresetIds,
      providers: config.providers.map(({ api_key, ...p }) => ({
        ...p,
        api_key_set:
          api_key === ""
            ? false
            : !!api_key || (p.id === provider.id && provider.api_key_set),
      })),
    };
    customApi.getCustom.mockResolvedValue(saved);
    return saved;
  });
  customApi.testCustom.mockResolvedValue({
    provider_id: "custom-1",
    success: true,
    response_time_ms: 10,
    result_count: 1,
  });
  setupApi.testSearch.mockResolvedValue({
    provider_id: "tavily",
    success: true,
    response_time_ms: 10,
    result_count: 1,
  });
  envApi.batchSaveEnvs.mockResolvedValue([]);
  envApi.deleteEnv.mockResolvedValue([]);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(window.getComputedStyle).mockRestore();
});

describe("<SearchConfigPage />", () => {
  it("shows built-in search when no provider is configured", async () => {
    mount();
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
  });

  it("shows the explicitly selected preset even when another preset is configured", async () => {
    mount({ providers: [provider], active_provider_id: "preset:brave" }, [
      "TAVILY_API_KEY",
      "BRAVE_API_KEY",
    ]);
    expect(
      await screen.findByText("当前搜索源：Brave Search"),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Brave Search" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
  });

  it("shows the explicitly selected custom engine", async () => {
    mount({ providers: [provider], active_provider_id: provider.id }, [
      "TAVILY_API_KEY",
    ]);
    expect(
      await screen.findByText("当前搜索源：My search"),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: provider.name })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
  });

  it("keeps configured presets off when built-in search is explicitly selected", async () => {
    mount({ providers: [provider], active_provider_id: null }, [
      "TAVILY_API_KEY",
    ]);
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
    expect(
      screen.getByRole("switch", { name: provider.name }),
    ).not.toBeChecked();
  });

  it("disables unconfigured preset switches while keeping their configuration entry available", async () => {
    mount();
    const switchControl = await screen.findByRole("switch", { name: "Tavily" });
    expect(switchControl).toBeDisabled();
    const card = screen.getByRole("button", { name: "Tavily" });
    expect(
      within(card).getByRole("button", {
        name: zh.advancedSettings.search.configure,
      }),
    ).toBeEnabled();
    fireEvent.click(switchControl);
    expect(customApi.saveCustom).not.toHaveBeenCalled();
  });

  it("allows turning off a selected preset whose key comes from the server process environment", async () => {
    mount({ providers: [], active_provider_id: "preset:tavily" });
    const switchControl = await screen.findByRole("switch", { name: "Tavily" });
    expect(switchControl).toBeChecked();
    expect(switchControl).not.toBeDisabled();
    fireEvent.keyDown(switchControl, { key: " ", keyCode: 32 });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(switchControl);
    await waitFor(() =>
      expect(customApi.saveCustom).toHaveBeenCalledWith({
        providers: [],
        active_provider_id: null,
      }),
    );
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
    expect(envApi.deleteEnv).not.toHaveBeenCalled();
  });

  it("can repeatedly enable and disable a preset configured in the process environment", async () => {
    mount({
      providers: [],
      active_provider_id: null,
      configured_preset_ids: ["tavily"],
    });
    const switchControl = await screen.findByRole("switch", { name: "Tavily" });
    expect(switchControl).not.toBeDisabled();
    fireEvent.click(switchControl);
    await waitFor(() => expect(switchControl).toBeChecked());
    fireEvent.click(switchControl);
    await waitFor(() => expect(switchControl).not.toBeChecked());
    expect(switchControl).not.toBeDisabled();
    fireEvent.click(switchControl);
    await waitFor(() => expect(switchControl).toBeChecked());
    expect(
      customApi.saveCustom.mock.calls.map(([body]) => body.active_provider_id),
    ).toEqual(["preset:tavily", null, "preset:tavily"]);
    expect(customApi.saveCustom.mock.calls[0][0]).not.toHaveProperty(
      "configured_preset_ids",
    );
    expect(envApi.batchSaveEnvs).not.toHaveBeenCalled();
    expect(envApi.deleteEnv).not.toHaveBeenCalled();
  });

  it("adds an engine with GET defaults without enabling it", async () => {
    mount();
    await openAdd();
    fireEvent.change(screen.getByLabelText(copy.apiKey), {
      target: { value: "new-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));

    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    const saved = customApi.saveCustom.mock.calls[0][0];
    expect(saved.providers[0]).toMatchObject({
      name: "New engine",
      url: "https://new.example.com/search",
      method: "GET",
      params: { q: "{query}", format: "json" },
      results_path: "results",
      api_key: "new-secret",
    });
    expect(saved.active_provider_id).toBeNull();
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("switch", { name: "New engine" }),
    ).not.toBeChecked();
  });

  it("preserves a selected preset when adding a custom engine", async () => {
    mount({ providers: [], active_provider_id: "preset:brave" }, [
      "BRAVE_API_KEY",
    ]);
    await openAdd();
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));
    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBe(
      "preset:brave",
    );
    expect(
      await screen.findByRole("switch", { name: "New engine" }),
    ).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "Brave Search" })).toBeChecked();
  });

  it("probes the unsaved form without changing saved configuration", async () => {
    mount();
    await openAdd();
    fireEvent.click(screen.getByText(copy.advanced));
    fireEvent.change(screen.getByLabelText(copy.params), {
      target: { value: '{"search":"{query}","key":"{api_key}"}' },
    });
    fireEvent.change(screen.getByLabelText(copy.apiKey), {
      target: { value: "draft-key" },
    });
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: zh.advancedSettings.search.probe,
      }),
    );

    await waitFor(() => expect(customApi.testCustom).toHaveBeenCalledOnce());
    expect(customApi.testCustom.mock.calls[0][0]).toMatchObject({
      name: "New engine",
      params: { search: "{query}", key: "{api_key}" },
      api_key: "draft-key",
    });
    expect(customApi.saveCustom).not.toHaveBeenCalled();
  });

  it("probes a saved custom engine from its card without saving or changing selection", async () => {
    mount({ providers: [provider], active_provider_id: "preset:tavily" }, [
      "TAVILY_API_KEY",
    ]);
    const card = await screen.findByRole("article", { name: provider.name });
    fireEvent.click(
      within(card).getByRole("button", {
        name: zh.advancedSettings.search.probe,
      }),
    );

    await waitFor(() => expect(customApi.testCustom).toHaveBeenCalledOnce());
    const { api_key_set: _apiKeySet, ...savedProvider } = provider;
    expect(customApi.testCustom).toHaveBeenCalledWith(savedProvider);
    expect(customApi.saveCustom).not.toHaveBeenCalled();
    expect(envApi.batchSaveEnvs).not.toHaveBeenCalled();
    expect(envApi.deleteEnv).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: "Tavily" })).toBeChecked();
    expect(
      screen.getByRole("switch", { name: provider.name }),
    ).not.toBeChecked();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("probes a preset from its card using server credentials while preserving the selected custom engine", async () => {
    mount({
      providers: [provider],
      active_provider_id: provider.id,
      configured_preset_ids: ["tavily"],
    });
    const card = await screen.findByRole("article", { name: "Tavily" });
    fireEvent.click(
      within(card).getByRole("button", {
        name: zh.advancedSettings.search.probe,
      }),
    );

    await waitFor(() => expect(setupApi.testSearch).toHaveBeenCalledOnce());
    expect(setupApi.testSearch).toHaveBeenCalledWith("tavily", {}, true);
    expect(customApi.saveCustom).not.toHaveBeenCalled();
    expect(envApi.batchSaveEnvs).not.toHaveBeenCalled();
    expect(envApi.deleteEnv).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: provider.name })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not probe an unconfigured preset from its card", async () => {
    mount();
    const card = await screen.findByRole("button", { name: "Tavily" });
    const probe = within(card).getByRole("button", {
      name: zh.advancedSettings.search.probe,
    });
    expect(probe).toBeDisabled();
    fireEvent.click(probe);
    expect(setupApi.testSearch).not.toHaveBeenCalled();
    expect(customApi.saveCustom).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("cannot delete preset credentials supplied only by the server process environment", async () => {
    mount({
      providers: [provider],
      active_provider_id: "preset:tavily",
      configured_preset_ids: ["tavily"],
    });
    const card = await screen.findByRole("article", { name: "Tavily" });
    const remove = within(card).getByRole("button", {
      name: zh.common.delete,
    });
    expect(remove).toBeDisabled();
    fireEvent.click(remove);
    expect(envApi.deleteEnv).not.toHaveBeenCalled();
    expect(customApi.saveCustom).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Tavily" })).toBeChecked();
  });

  it.each([
    ["preset:tavily", null],
    [provider.id, provider.id],
  ])(
    "deletes preset credentials from the card while preserving its catalog entry and custom configuration (%s)",
    async (selected, expectedSelection) => {
      envApi.deleteEnv.mockImplementationOnce(async () => {
        envApi.listEnvs.mockResolvedValue(envResp(["BRAVE_API_KEY"]));
        return [];
      });
      mount({ providers: [provider], active_provider_id: selected }, [
        "TAVILY_API_KEY",
        "BRAVE_API_KEY",
      ]);
      const card = await screen.findByRole("article", { name: "Tavily" });
      fireEvent.click(
        within(card).getByRole("button", { name: zh.common.delete }),
      );
      const confirm = await screen.findByRole("dialog");
      expect(confirm).toHaveAccessibleName(
        zh.setupWizard.search.revokeTitle.replace("{{name}}", "Tavily"),
      );
      fireEvent.click(
        within(confirm).getByRole("button", {
          name: zh.setupWizard.search.revoke,
        }),
      );

      await waitFor(() => expect(envApi.deleteEnv).toHaveBeenCalledOnce());
      expect(envApi.deleteEnv).toHaveBeenCalledWith("TAVILY_API_KEY");
      expect(customApi.saveCustom).toHaveBeenCalledOnce();
      const saved = customApi.saveCustom.mock.calls[0][0];
      expect(saved.active_provider_id).toBe(expectedSelection);
      expect(saved.providers).toHaveLength(1);
      expect(saved.providers[0]).toMatchObject({
        id: provider.id,
        name: provider.name,
        url: provider.url,
      });
      expect(saved.providers[0]).not.toHaveProperty("api_key");
      expect(customApi.saveCustom.mock.invocationCallOrder[0]).toBeLessThan(
        envApi.deleteEnv.mock.invocationCallOrder[0],
      );
      const unconfiguredCard = await screen.findByRole("button", {
        name: "Tavily",
      });
      expect(
        within(unconfiguredCard).getByRole("switch", { name: "Tavily" }),
      ).toBeDisabled();
      expect(
        within(unconfiguredCard).getByRole("button", {
          name: zh.advancedSettings.search.configure,
        }),
      ).toBeEnabled();
      expect(
        await screen.findByRole("article", { name: provider.name }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("switch", { name: provider.name }),
      ).toHaveAttribute(
        "aria-checked",
        String(expectedSelection === provider.id),
      );
      expect(
        screen.getByRole("switch", { name: "Brave Search" }),
      ).toBeEnabled();
      expect(envApi.batchSaveEnvs).not.toHaveBeenCalled();
    },
  );

  it("adds an engine when randomUUID is unavailable on a LAN HTTP origin", async () => {
    vi.stubGlobal("crypto", {});
    mount();
    await openAdd();
    fireEvent.change(screen.getByLabelText(copy.url), {
      target: { value: "http://searxng:8080/search" },
    });
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));
    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    const saved = customApi.saveCustom.mock.calls[0][0];
    expect(saved.providers[0].id).toMatch(/^custom-[a-z0-9]+-[a-z0-9]+$/);
    expect(saved.providers[0].url).toBe("http://searxng:8080/search");
    expect(saved.active_provider_id).toBeNull();
  });

  it("submits a POST JSON body and supports root arrays with optional result fields", async () => {
    mount();
    await openAdd();
    const method = screen.getByRole("combobox");
    fireEvent.mouseDown(method);
    fireEvent.keyDown(method, { key: "ArrowDown", keyCode: 40 });
    fireEvent.keyDown(method, { key: "Enter", keyCode: 13 });
    fireEvent.click(screen.getByText(copy.advanced));
    fireEvent.change(screen.getByLabelText(copy.body), {
      target: {
        value: '{"search":{"query":"{query}"},"limit":"{max_results}"}',
      },
    });
    for (const label of [
      copy.resultsPath,
      copy.title_path,
      copy.content_path,
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
    }
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));
    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].providers[0]).toMatchObject({
      method: "POST",
      body: { search: { query: "{query}" }, limit: "{max_results}" },
      results_path: "",
      title_path: "",
      content_path: "",
      url_path: "url",
    });
  });

  it("edits an engine while preserving its stored key and inactive state", async () => {
    mount({ providers: [provider], active_provider_id: null });
    await openEdit();
    expect(screen.getByText(copy.keyStoredHint)).toBeInTheDocument();
    expect(screen.getByLabelText(copy.apiKey)).toHaveValue("");
    fireEvent.change(screen.getByLabelText(copy.name), {
      target: { value: "Renamed engine" },
    });
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));

    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    const saved = customApi.saveCustom.mock.calls[0][0];
    expect(saved.active_provider_id).toBeNull();
    expect(saved.providers[0]).toMatchObject({
      id: provider.id,
      name: "Renamed engine",
    });
    expect(saved.providers[0]).not.toHaveProperty("api_key");
    expect(saved.providers[0]).not.toHaveProperty("api_key_set");
  });

  it("clears the stored key only when explicitly selected", async () => {
    mount({ providers: [provider], active_provider_id: provider.id });
    await openEdit();
    fireEvent.click(screen.getByLabelText(copy.clearKey));
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));

    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].providers[0].api_key).toBe("");
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBe(
      provider.id,
    );
  });

  it("activates a saved engine without sending a key or response-only fields", async () => {
    mount({ providers: [provider], active_provider_id: "preset:tavily" }, [
      "TAVILY_API_KEY",
    ]);
    fireEvent.click(await screen.findByRole("switch", { name: provider.name }));

    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBe(
      provider.id,
    );
    expect(
      customApi.saveCustom.mock.calls[0][0].providers[0],
    ).not.toHaveProperty("api_key");
    expect(
      customApi.saveCustom.mock.calls[0][0].providers[0],
    ).not.toHaveProperty("api_key_set");
    expect(
      await screen.findByText("当前搜索源：My search"),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
  });

  it("switches from a custom engine to a preset while keeping custom configuration", async () => {
    mount({ providers: [provider], active_provider_id: provider.id }, [
      "TAVILY_API_KEY",
    ]);
    fireEvent.click(await screen.findByRole("switch", { name: "Tavily" }));

    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBe(
      "preset:tavily",
    );
    expect(customApi.saveCustom.mock.calls[0][0].providers).toHaveLength(1);
    expect(await screen.findByText("当前搜索源：Tavily")).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: provider.name }),
    ).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "Tavily" })).toBeChecked();
  });

  it("switches exclusively between configured presets", async () => {
    mount({ providers: [provider], active_provider_id: "preset:tavily" }, [
      "TAVILY_API_KEY",
      "BRAVE_API_KEY",
    ]);
    fireEvent.click(
      await screen.findByRole("switch", { name: "Brave Search" }),
    );
    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBe(
      "preset:brave",
    );
    await waitFor(() =>
      expect(
        screen.getByRole("switch", { name: "Brave Search" }),
      ).toBeChecked(),
    );
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
    expect(
      screen.getByRole("switch", { name: provider.name }),
    ).not.toBeChecked();
  });

  it("turns off a selected preset without deleting its credentials or custom configurations", async () => {
    mount({ providers: [provider], active_provider_id: "preset:tavily" }, [
      "TAVILY_API_KEY",
    ]);
    fireEvent.click(await screen.findByRole("switch", { name: "Tavily" }));
    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBeNull();
    expect(customApi.saveCustom.mock.calls[0][0].providers).toHaveLength(1);
    expect(envApi.deleteEnv).not.toHaveBeenCalled();
    expect(envApi.batchSaveEnvs).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeDisabled();
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
  });

  it("keeps selection unchanged and blocks other switches while a save is pending", async () => {
    let finish!: (config: CustomSearchConfig) => void;
    customApi.saveCustom.mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    mount({ providers: [provider], active_provider_id: provider.id }, [
      "TAVILY_API_KEY",
    ]);
    fireEvent.click(await screen.findByRole("switch", { name: "Tavily" }));
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: provider.name })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Tavily" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: provider.name })).toBeDisabled();
    fireEvent.click(screen.getByRole("switch", { name: provider.name }));
    expect(customApi.saveCustom).toHaveBeenCalledOnce();
    finish({ providers: [provider], active_provider_id: "preset:tavily" });
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Tavily" })).toBeChecked(),
    );
    expect(
      screen.getByRole("switch", { name: provider.name }),
    ).not.toBeChecked();
  });

  it("keeps the selected engine when saving a switch change fails", async () => {
    customApi.saveCustom.mockRejectedValueOnce(new Error("network down"));
    mount({ providers: [provider], active_provider_id: provider.id }, [
      "TAVILY_API_KEY",
    ]);
    fireEvent.click(await screen.findByRole("switch", { name: "Tavily" }));
    expect(await screen.findByText("network down")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: provider.name })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
    expect(
      screen.getByRole("switch", { name: provider.name }),
    ).not.toBeDisabled();
  });

  it("preserves the selected custom engine when saving preset credentials", async () => {
    mount({ providers: [provider], active_provider_id: provider.id }, [
      "TAVILY_API_KEY",
    ]);
    const card = await screen.findByRole("article", { name: "Tavily" });
    fireEvent.click(within(card).getByRole("button", { name: zh.common.edit }));
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));
    await waitFor(() => expect(envApi.batchSaveEnvs).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBe(
      provider.id,
    );
    expect(customApi.saveCustom.mock.calls[0][0].providers).toHaveLength(1);
    expect(customApi.saveCustom.mock.invocationCallOrder[0]).toBeLessThan(
      envApi.batchSaveEnvs.mock.invocationCallOrder[0],
    );
    expect(
      await screen.findByText("当前搜索源：My search"),
    ).toBeInTheDocument();
  });

  it("keeps built-in search selected after configuring a previously unconfigured preset", async () => {
    envApi.batchSaveEnvs.mockImplementationOnce(async (values) => {
      envApi.listEnvs.mockResolvedValue(envResp(Object.keys(values)));
      return [];
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Tavily" }));
    fireEvent.change(screen.getByLabelText("TAVILY_API_KEY"), {
      target: { value: "new-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));
    await waitFor(() => expect(envApi.batchSaveEnvs).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBeNull();
    expect(customApi.saveCustom.mock.invocationCallOrder[0]).toBeLessThan(
      envApi.batchSaveEnvs.mock.invocationCallOrder[0],
    );
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeDisabled();
  });

  it("turns off a selected preset when its credentials are revoked", async () => {
    mount({ providers: [provider], active_provider_id: "preset:tavily" }, [
      "TAVILY_API_KEY",
    ]);
    const card = await screen.findByRole("article", { name: "Tavily" });
    fireEvent.click(within(card).getByRole("button", { name: zh.common.edit }));
    fireEvent.click(
      screen.getByRole("button", { name: zh.setupWizard.search.revoke }),
    );
    const [title] = await screen.findAllByText(
      zh.setupWizard.search.revokeTitle.replace("{{name}}", "Tavily"),
    );
    const confirm = title.closest('[role="dialog"]') as HTMLElement;
    fireEvent.click(
      within(confirm).getByRole("button", {
        name: zh.setupWizard.search.revoke,
      }),
    );
    await waitFor(() =>
      expect(envApi.deleteEnv).toHaveBeenCalledWith("TAVILY_API_KEY"),
    );
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBeNull();
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
  });

  it("deletes the selected custom engine and returns to built-in search", async () => {
    mount({ providers: [provider], active_provider_id: provider.id }, [
      "TAVILY_API_KEY",
    ]);
    const card = await screen.findByRole("article", { name: provider.name });
    fireEvent.click(
      within(card).getByRole("button", { name: zh.common.delete }),
    );
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: zh.common.delete,
      }),
    );

    await waitFor(() =>
      expect(customApi.saveCustom).toHaveBeenCalledWith({
        providers: [],
        active_provider_id: null,
      }),
    );
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Tavily" })).not.toBeChecked();
  });

  it("switches back to built-in search without deleting a custom engine", async () => {
    mount({ providers: [provider], active_provider_id: provider.id });
    fireEvent.click(await screen.findByRole("switch", { name: provider.name }));
    await waitFor(() => expect(customApi.saveCustom).toHaveBeenCalledOnce());
    expect(customApi.saveCustom.mock.calls[0][0].active_provider_id).toBeNull();
    expect(customApi.saveCustom.mock.calls[0][0].providers).toHaveLength(1);
    expect(
      await screen.findByText(zh.advancedSettings.search.sourceBuiltinTitle),
    ).toBeInTheDocument();
  });

  it("rejects query parameter JSON with non-string values", async () => {
    mount();
    await openAdd();
    fireEvent.click(screen.getByText(copy.advanced));
    fireEvent.change(screen.getByLabelText(copy.params), {
      target: { value: '{"q":42}' },
    });
    fireEvent.click(screen.getByRole("button", { name: zh.common.save }));

    expect(
      await screen.findByText(copy.stringObjectRequired),
    ).toBeInTheDocument();
    expect(customApi.saveCustom).not.toHaveBeenCalled();
  });

  it("does not allow overwriting saved engines when the configuration fails to load", async () => {
    customApi.getCustom.mockRejectedValue(new Error("unavailable"));
    mount();
    expect(
      await screen.findByRole("button", { name: zh.common.retry }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: copy.add }),
    ).not.toBeInTheDocument();
  });
});
