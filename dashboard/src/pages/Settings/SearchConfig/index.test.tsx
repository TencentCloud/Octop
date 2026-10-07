/**
 * SearchConfig.test.tsx — search provider settings page.
 *
 * Covers the search-source hint introduced for #109:
 *   - no provider configured → built-in search hint is shown
 *   - a provider configured → it is shown as the current search source
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("../../../api/modules/env", () => ({
  envsApi: {
    listEnvs: vi.fn(),
    batchSaveEnvs: vi.fn(),
    deleteEnv: vi.fn(),
  },
}));

import { envsApi } from "../../../api/modules/env";
import SearchConfigPage from "./index";

const api = vi.mocked(envsApi, true);

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

    expect(screen.getByText("当前搜索源：内置搜索")).toBeInTheDocument();
  });

  it("shows the configured provider as the current search source", async () => {
    api.listEnvs.mockResolvedValue(envResp(["TAVILY_API_KEY"]));

    render(<SearchConfigPage />);
    await waitFor(() => expect(api.listEnvs).toHaveBeenCalled());

    expect(screen.getByText("当前搜索源：Tavily")).toBeInTheDocument();
  });

  it("prioritizes a configured custom search provider", async () => {
    api.listEnvs.mockResolvedValue(
      envResp([
        "TAVILY_API_KEY",
        "CUSTOM_SEARCH_URL",
        "CUSTOM_SEARCH_API_KEY",
        "CUSTOM_SEARCH_PROTOCOL",
      ]),
    );
    render(<SearchConfigPage />);
    expect(
      await screen.findByText("当前搜索源：Custom Search"),
    ).toBeInTheDocument();
  });

  it("does not activate custom search with incomplete configuration", async () => {
    api.listEnvs.mockResolvedValue(
      envResp(["CUSTOM_SEARCH_URL", "TAVILY_API_KEY"]),
    );
    render(<SearchConfigPage />);
    expect(await screen.findByText("当前搜索源：Tavily")).toBeInTheDocument();
  });
});
