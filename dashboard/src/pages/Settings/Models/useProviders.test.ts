import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useProviders } from "./useProviders";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../../../api/request", () => ({
  request,
  bridgeAgentHeaders: () => ({}),
}));

vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});

let globalModel: { provider_name: string; model: string };
let preferredModel: string | null;

beforeEach(() => {
  globalModel = { provider_name: "OpenRouter", model: "global/model" };
  preferredModel = "Other/chat/model";
  request.mockReset();
  request.mockImplementation(async (path: string) => {
    if (path === "/providers/active-model") return globalModel;
    if (path === "/preferences") {
      return { preferred_model: preferredModel, model_reasoning: {} };
    }
    return [];
  });
});

describe("useProviders model defaults", () => {
  it("keeps the global default separate from the personal preference", async () => {
    const { result } = renderHook(() => useProviders());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.globalActiveModel).toEqual(globalModel);
    expect(result.current.preferredModel).toBe("Other/chat/model");
  });

  it("does not turn the global default into an explicit personal preference", async () => {
    preferredModel = null;
    const { result } = renderHook(() => useProviders());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.globalActiveModel).toEqual(globalModel);
    expect(result.current.preferredModel).toBe("");
  });

  it("refreshes either setting without deriving it from the other", async () => {
    const { result } = renderHook(() => useProviders());
    await waitFor(() => expect(result.current.loading).toBe(false));

    globalModel = { provider_name: "OpenRouter", model: "new/global" };
    await act(() => result.current.fetchAll());
    expect(result.current.globalActiveModel).toEqual(globalModel);
    expect(result.current.preferredModel).toBe("Other/chat/model");

    preferredModel = "Other/new/chat";
    await act(() => result.current.fetchAll());
    expect(result.current.preferredModel).toBe("Other/new/chat");
    expect(result.current.globalActiveModel).toEqual(globalModel);
  });
});
