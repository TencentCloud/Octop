/**
 * SearchConfig.test.tsx — search provider settings page.
 *
 * Covers the search-source hint introduced for #109:
 *   - no provider configured → built-in search hint is shown
 *   - a provider configured → it is shown as the current search source
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App as AntdApp } from "antd";

vi.mock("../../../api/modules/env", () => ({
  envsApi: {
    listEnvs: vi.fn(),
    batchSaveEnvs: vi.fn(),
    deleteEnv: vi.fn(),
  },
}));

vi.mock("../../../api", () => ({
  default: {
    testSearch: vi.fn(),
    importDeepSeekModelKey: vi.fn(),
  },
}));

// The DeepSeek "reuse model provider key" action needs providers + envs rights.
vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ role: "admin", permissions: [] }),
}));

import { envsApi } from "../../../api/modules/env";
import rootApi from "../../../api";
import SearchConfigPage from "./index";

const api = vi.mocked(envsApi, true);
const deepseekApi = rootApi as unknown as {
  testSearch: ReturnType<typeof vi.fn>;
  importDeepSeekModelKey: ReturnType<typeof vi.fn>;
};

function envResp(keys: string[]) {
  return keys.map((key, i) => ({ key, value: `v${i}` })) as never;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<SearchConfigPage />", () => {
  it("shows the built-in search hint when no provider is configured", async () => {
    api.listEnvs.mockResolvedValue(envResp([]));

    render(<SearchConfigPage />);
    await waitFor(() => expect(api.listEnvs).toHaveBeenCalled());

    expect(
      screen.getByText("advancedSettings.search.desc"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "搜索引擎" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("当前搜索源：内置搜索")).toBeInTheDocument();
  });

  it("shows the configured provider as the current search source", async () => {
    api.listEnvs.mockResolvedValue(envResp(["TAVILY_API_KEY"]));

    render(<SearchConfigPage />);
    await waitFor(() => expect(api.listEnvs).toHaveBeenCalled());

    expect(screen.getByText("当前搜索源：Tavily")).toBeInTheDocument();
  });

  it("shows DeepSeek Search when its API key is configured", async () => {
    api.listEnvs.mockResolvedValue(envResp(["DEEPSEEK_API_KEY"]));

    render(<SearchConfigPage />);
    await waitFor(() => expect(api.listEnvs).toHaveBeenCalled());

    expect(screen.getByText("当前搜索源：DeepSeek Search")).toBeInTheDocument();
    expect(screen.getByText("DeepSeek Search")).toBeInTheDocument();
  });

  it("accepts the search-only DEEPSEEK_SEARCH_API_KEY alias", async () => {
    api.listEnvs.mockResolvedValue(envResp(["DEEPSEEK_SEARCH_API_KEY"]));

    render(<SearchConfigPage />);
    await waitFor(() => expect(api.listEnvs).toHaveBeenCalled());

    expect(screen.getByText("当前搜索源：DeepSeek Search")).toBeInTheDocument();
  });

  it("prefills and probes the DeepSeek key from the search-only alias", async () => {
    api.listEnvs.mockResolvedValue([
      { key: "DEEPSEEK_SEARCH_API_KEY", value: "sk-alias" },
    ] as never);
    deepseekApi.testSearch.mockResolvedValue({ success: true });

    render(
      <AntdApp>
        <SearchConfigPage />
      </AntdApp>,
    );
    await waitFor(() => expect(api.listEnvs).toHaveBeenCalled());

    // The provider is configured via the alias, so the card exposes Edit.
    fireEvent.click(screen.getByText("common.edit"));

    const apiKeyInput = (await screen.findByLabelText(
      "setupWizard.search.deepseek.apiKey",
    )) as HTMLInputElement;
    expect(apiKeyInput.value).toBe("sk-alias");

    fireEvent.click(screen.getByText("advancedSettings.search.probe"));
    await waitFor(() => expect(deepseekApi.testSearch).toHaveBeenCalled());
    expect(deepseekApi.testSearch).toHaveBeenCalledWith(
      "deepseek",
      expect.objectContaining({ DEEPSEEK_API_KEY: "sk-alias" }),
    );
  });

  it("configures DeepSeek search options and can reuse the model provider key", async () => {
    api.listEnvs.mockResolvedValue(envResp([]));
    deepseekApi.importDeepSeekModelKey.mockResolvedValue({
      ok: true,
      provider_name: "DeepSeek",
    });

    render(
      <AntdApp>
        <SearchConfigPage />
      </AntdApp>,
    );
    await waitFor(() => expect(api.listEnvs).toHaveBeenCalled());

    fireEvent.click(screen.getByText("DeepSeek Search"));

    // react-i18next is auto-mocked in tests, so ``t(key)`` returns the key.
    expect(
      await screen.findByText("setupWizard.search.deepseek.baseUrl"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("setupWizard.search.deepseek.apiKey"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("setupWizard.search.deepseek.count"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("setupWizard.search.deepseek.needContent"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("setupWizard.search.deepseek.localization"),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByText("setupWizard.search.deepseek.reuseModelKey"),
    );
    await waitFor(() =>
      expect(deepseekApi.importDeepSeekModelKey).toHaveBeenCalledTimes(1),
    );
  });
});
