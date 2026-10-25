import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { preferencesApi } from "../../../../../api/modules/preferences";
import { providerApi } from "../../../../../api/modules/provider";
import { request } from "../../../../../api/request";
import type { UserPreferences } from "../../../../../api/modules/preferences";
import { message } from "../../../../../utils/antdMessage";
import { useProviders } from "../../useProviders";
import { ActiveModelPool } from "./ActiveModelPool";

const { translate } = vi.hoisted(() => ({
  translate: (key: string) => key,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate }),
}));
vi.mock("../../../../../api/modules/preferences", () => ({
  preferencesApi: { get: vi.fn(), patch: vi.fn() },
}));
vi.mock("../../../../../api/modules/provider", () => ({
  providerApi: { listResolvedModels: vi.fn() },
}));
vi.mock("../../../../../api/request", () => ({ request: vi.fn() }));
vi.mock("../../../../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

let savedPreference: string | null;

function preferences(): UserPreferences {
  return {
    locale: "zh",
    remote_browser_bookmarks: [],
    preferred_model: savedPreference,
    model_reasoning: {},
  };
}

function ModelPool() {
  const { loading, fetchAll, ...data } = useProviders();
  return loading ? null : <ActiveModelPool {...data} onSaved={fetchAll} />;
}

beforeEach(() => {
  vi.clearAllMocks();
  savedPreference = null;
  vi.mocked(preferencesApi.get).mockImplementation(async () => preferences());
  vi.mocked(preferencesApi.patch).mockImplementation(async (body) => {
    savedPreference = body.preferred_model ?? null;
    return preferences();
  });
  vi.mocked(providerApi.listResolvedModels).mockResolvedValue(
    ["a", "b"].map((model) => ({
      provider_id: 1,
      provider_name: "prov",
      provider_kind: "openai",
      model,
      name: `Model ${model.toUpperCase()}`,
    })),
  );
  vi.mocked(request).mockImplementation(async (path) => {
    if (path === "/providers/active-model") {
      return { provider_name: "prov", model: "a" };
    }
    return [];
  });
});

describe("ActiveModelPool personal preference", () => {
  it("leaves stars unselected when no personal preference is set", async () => {
    render(<ModelPool />);

    const star = await screen.findByRole("button", {
      name: "models.setAsPreferred: prov / Model A",
    });
    expect(star).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
    expect(request).not.toHaveBeenCalledWith("/providers/active-model");
  });

  it("reports an initial preference load failure instead of assuming no preference", async () => {
    vi.mocked(preferencesApi.get).mockRejectedValueOnce(new Error("offline"));
    const { result } = renderHook(() => useProviders());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("offline");
  });

  it("preserves the last loaded preference and reasoning when refreshing fails", async () => {
    savedPreference = "prov/a";
    const reasoning = {
      "prov/a": { mode: "enabled" as const, effort: "high" },
    };
    vi.mocked(preferencesApi.get).mockResolvedValueOnce({
      ...preferences(),
      model_reasoning: reasoning,
    });
    const { result } = renderHook(() => useProviders());
    await waitFor(() => expect(result.current.loading).toBe(false));

    vi.mocked(preferencesApi.get).mockRejectedValueOnce(new Error("offline"));
    await act(async () => result.current.fetchAll());

    expect(result.current.error).toBe("offline");
    expect(result.current.activeModel).toEqual({
      provider_name: "prov",
      model: "a",
    });
    expect(result.current.modelReasoning).toEqual(reasoning);
  });

  it("sets and clears a preference, keeping it cleared after a remount", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<ModelPool />);
    await user.click(
      await screen.findByRole("button", {
        name: "models.setAsPreferred: prov / Model A",
      }),
    );
    expect(preferencesApi.patch).toHaveBeenLastCalledWith({
      preferred_model: "prov/a",
    });

    const selected = await screen.findByRole("button", {
      name: "models.clearPreferred: prov / Model A",
    });
    expect(selected).toHaveAttribute("aria-pressed", "true");
    await user.click(selected);

    await waitFor(() =>
      expect(preferencesApi.patch).toHaveBeenLastCalledWith({
        preferred_model: null,
      }),
    );
    await screen.findByRole("button", {
      name: "models.setAsPreferred: prov / Model A",
    });
    expect(message.success).toHaveBeenLastCalledWith(
      "models.preferredModelCleared",
    );
    expect(savedPreference).toBeNull();
    unmount();

    render(<ModelPool />);
    await screen.findByRole("button", {
      name: "models.setAsPreferred: prov / Model A",
    });
    expect(screen.queryByRole("button", { pressed: true })).toBeNull();
    expect(request).not.toHaveBeenCalledWith(
      "/providers/active-model",
      expect.objectContaining({ method: "PUT" }),
    );
  });

  it("can switch the personal preference to another model", async () => {
    savedPreference = "prov/a";
    const user = userEvent.setup();
    render(<ModelPool />);
    await user.click(
      await screen.findByRole("button", {
        name: "models.setAsPreferred: prov / Model B",
      }),
    );

    const selected = await screen.findByRole("button", {
      name: "models.clearPreferred: prov / Model B",
    });
    expect(selected).toHaveAttribute("aria-pressed", "true");
    expect(preferencesApi.patch).toHaveBeenLastCalledWith({
      preferred_model: "prov/b",
    });
    expect(
      screen.getByRole("button", {
        name: "models.setAsPreferred: prov / Model A",
      }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("preserves the preference when clearing it fails", async () => {
    savedPreference = "prov/a";
    vi.mocked(preferencesApi.patch).mockRejectedValueOnce(new Error("offline"));
    const user = userEvent.setup();
    render(<ModelPool />);
    await user.click(
      await screen.findByRole("button", {
        name: "models.clearPreferred: prov / Model A",
      }),
    );

    await waitFor(() => expect(message.error).toHaveBeenCalledWith("offline"));
    expect(savedPreference).toBe("prov/a");
    expect(screen.getByRole("button", { pressed: true })).toHaveAccessibleName(
      "models.clearPreferred: prov / Model A",
    );
  });

  it("disables preference changes while a save is pending", async () => {
    let finish!: (value: UserPreferences) => void;
    vi.mocked(preferencesApi.patch).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<ModelPool />);
    await user.click(
      await screen.findByRole("button", {
        name: "models.setAsPreferred: prov / Model A",
      }),
    );
    expect(
      screen.getByRole("button", {
        name: "models.setAsPreferred: prov / Model B",
      }),
    ).toBeDisabled();
    expect(preferencesApi.patch).toHaveBeenCalledTimes(1);

    savedPreference = "prov/a";
    await act(async () => finish(preferences()));
    expect(
      screen.getByRole("button", {
        name: "models.setAsPreferred: prov / Model B",
      }),
    ).toBeEnabled();
  });
});
