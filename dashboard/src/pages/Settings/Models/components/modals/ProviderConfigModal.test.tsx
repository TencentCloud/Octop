import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "../../../../../api/request";
import type {
  ProviderModel,
  ProviderPreset,
  ProviderRow,
} from "../../useProviders";
import { ProviderConfigModal } from "./ProviderConfigModal";

vi.mock("../../../../../api/request", () => ({ request: vi.fn() }));
vi.mock("./ModelListEditor", () => ({
  ModelListEditor: ({
    models,
    onModelsChange,
  }: {
    models: ProviderModel[];
    onModelsChange: (models: ProviderModel[]) => void;
  }) => (
    <div>
      {models.map((model) => (
        <label key={model.id}>
          {model.id}
          <input
            type="checkbox"
            checked={model.enabled}
            onChange={() =>
              onModelsChange(
                models.map((item) =>
                  item.id === model.id
                    ? { ...item, enabled: !item.enabled }
                    : item,
                ),
              )
            }
          />
        </label>
      ))}
    </div>
  ),
}));

const provider: ProviderRow = {
  id: 7,
  name: "Tencent Cloud Hy Token Plan",
  kind: "openai",
  base_url: "https://my-proxy.example/v1",
  api_key: "existing-key",
  models: [{ id: "hy3", name: "My Hy3", enabled: true, max_tokens: 1024 }],
  note: "keep my settings",
  enabled: true,
};
const preset: ProviderPreset = {
  id: "tencent-hy-token-plan",
  name: provider.name,
  protocol: "openai",
  base_url: "https://api.lkeap.cloud.tencent.com/plan/v3",
  api_key_prefix: "sk-tp-",
  models: [
    { id: "hy4", name: "Hy4", max_output_tokens: 64_000, reasoning: true },
    { id: "hy3", name: "Hy3" },
  ],
};

function renderConfig(presetId?: string, currentProvider = provider) {
  const onClose = vi.fn();
  render(
    <App>
      <ProviderConfigModal
        provider={currentProvider}
        presetId={presetId}
        open
        onClose={onClose}
        onSaved={vi.fn()}
        apiPrefix="/admin/providers"
      />
    </App>,
  );
  return { onClose };
}

describe("provider preset sync", () => {
  it("shows package controls while keeping the default separate from display order", () => {
    renderConfig(preset.id, {
      ...provider,
      model_catalog_locked: true,
      default_model: "hy3",
      models: [{ id: "hy4", name: "Hy4", enabled: true }, provider.models[0]],
    });
    expect(
      screen.queryByRole("button", { name: "models.fetchModels" }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "models.syncPreset" }),
    ).toBeInTheDocument();
    expect(screen.getByText("My Hy3 (hy3)")).toBeInTheDocument();
  });
  beforeEach(() => {
    vi.mocked(request).mockReset();
    vi.mocked(request).mockResolvedValue([preset]);
  });

  it("fetches the current preset and saves only model changes after explicit enable and save", async () => {
    const user = userEvent.setup();
    renderConfig(preset.id);
    expect(request).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "models.syncPreset" }));
    expect(
      await screen.findByRole("checkbox", { name: "hy4" }),
    ).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "hy3" })).toBeChecked();
    expect(request).toHaveBeenCalledExactlyOnceWith("/providers/presets");

    await user.click(screen.getByRole("checkbox", { name: "hy4" }));
    await user.click(screen.getByRole("button", { name: "common.save" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const [path, options] = vi.mocked(request).mock.calls[1];
    expect(path).toBe("/admin/providers/7");
    expect(options?.method).toBe("PATCH");
    expect(JSON.parse(options?.body as string)).toEqual({
      models: [
        provider.models[0],
        {
          id: "hy4",
          name: "Hy4",
          enabled: true,
          input: ["text"],
          thinking: null,
          reasoning: true,
          max_tokens: 64_000,
        },
      ],
    });
  });

  it("can cancel syncing without persisting any changes", async () => {
    const user = userEvent.setup();
    const { onClose } = renderConfig(preset.id);
    await user.click(screen.getByRole("button", { name: "models.syncPreset" }));
    await screen.findByRole("checkbox", { name: "hy4" });
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(request).toHaveBeenCalledExactlyOnceWith("/providers/presets");
  });

  it("preserves model edits made while preset loading is in progress", async () => {
    let finishLoading!: (presets: ProviderPreset[]) => void;
    vi.mocked(request).mockReturnValueOnce(
      new Promise<ProviderPreset[]>((resolve) => {
        finishLoading = resolve;
      }),
    );
    const user = userEvent.setup();
    renderConfig(preset.id);
    await user.click(screen.getByRole("button", { name: "models.syncPreset" }));
    await user.click(screen.getByRole("checkbox", { name: "hy3" }));
    expect(screen.getByRole("button", { name: "common.save" })).toBeDisabled();

    finishLoading([preset]);
    expect(
      await screen.findByRole("checkbox", { name: "hy4" }),
    ).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "hy3" })).not.toBeChecked();
  });

  it("does not offer preset sync for custom providers", () => {
    renderConfig();
    expect(
      screen.queryByRole("button", { name: "models.syncPreset" }),
    ).toBeNull();
  });
});
