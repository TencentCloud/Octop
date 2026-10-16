import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { listResolvedModels, request } = vi.hoisted(() => ({
  listResolvedModels: vi.fn(),
  request: vi.fn(),
}));

vi.mock("../api/modules/provider", () => ({
  providerApi: { listResolvedModels },
}));

vi.mock("../api/request", () => ({ request }));

vi.mock("../pages/Admin/Storage/useStorageBackends", () => ({
  isAgentResolvableStorageKind: (kind: string) => kind === "s3",
}));

import { useAgentFormResources } from "./useAgentFormResources";

describe("useAgentFormResources", () => {
  beforeEach(() => {
    listResolvedModels.mockReset();
    request.mockReset();
    listResolvedModels.mockResolvedValue([{ id: "peer-model" }]);
    request.mockResolvedValue([
      { id: 1, name: "local-s3", kind: "s3", enabled: true },
    ]);
  });

  it("loads local models and storage backends without an agent id", async () => {
    const { result } = renderHook(() => useAgentFormResources(true));

    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(listResolvedModels).toHaveBeenCalledWith(undefined);
    expect(request).toHaveBeenCalledWith("/storage-backends");
    expect(result.current.models).toEqual([{ id: "peer-model" }]);
    expect(result.current.backends).toEqual([
      { id: 1, name: "local-s3", kind: "s3", enabled: true },
    ]);
  });

  it("tunnels model lists for a peer expert and skips local storage backends", async () => {
    const agentId = "bridge:c1:doctor";
    const { result } = renderHook(() => useAgentFormResources(true, agentId));

    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(listResolvedModels).toHaveBeenCalledWith(agentId);
    expect(request).not.toHaveBeenCalled();
    expect(result.current.backends).toEqual([]);
    expect(result.current.backendsLoading).toBe(false);
  });
});
