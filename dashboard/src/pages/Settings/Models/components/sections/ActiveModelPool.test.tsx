import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { preferencesApi } from "../../../../../api/modules/preferences";
import type { ResolvedModel } from "../../useProviders";
import { ActiveModelPool } from "./ActiveModelPool";

vi.mock("../../../../../api/modules/preferences", () => ({
  preferencesApi: {
    get: vi.fn(),
    patch: vi.fn().mockResolvedValue({}),
  },
}));

const models: ResolvedModel[] = [
  {
    provider_id: 1,
    provider_name: "prov-a",
    provider_kind: "openai",
    model: "model-a",
    name: "Model A",
  },
  {
    provider_id: 1,
    provider_name: "prov-a",
    provider_kind: "openai",
    model: "model-b",
    name: "Model B",
  },
];

function renderPool(preferredModel: string | null) {
  return render(
    <App>
      <ActiveModelPool
        resolvedModels={models}
        preferredModel={preferredModel}
        globalActiveModel={{ provider_name: "prov-a", model: "model-a" }}
        providers={[]}
        modelReasoning={{}}
        onSaved={vi.fn()}
      />
    </App>,
  );
}

/** Each row renders exactly one button (the star) when providers lack keys. */
function starButtonFor(label: string): HTMLElement {
  const info = screen.getByText(label).closest("div");
  const row = info?.parentElement;
  if (!row) throw new Error(`row for ${label} not found`);
  return within(row).getByRole("button");
}

describe("ActiveModelPool preferred model star", () => {
  beforeEach(() => {
    vi.mocked(preferencesApi.patch).mockClear();
  });

  it("clears the personal preference when the lit star is clicked again", async () => {
    const user = userEvent.setup();
    renderPool("prov-a/model-a");

    await user.click(starButtonFor("prov-a / Model A"));

    await waitFor(() =>
      expect(preferencesApi.patch).toHaveBeenCalledWith({
        preferred_model: null,
      }),
    );
  });

  it("sets a different model as the personal preference", async () => {
    const user = userEvent.setup();
    renderPool("prov-a/model-a");

    await user.click(starButtonFor("prov-a / Model B"));

    await waitFor(() =>
      expect(preferencesApi.patch).toHaveBeenCalledWith({
        preferred_model: "prov-a/model-b",
      }),
    );
  });

  it("marks the global default with a badge instead of a lit star when no preference is set", async () => {
    const user = userEvent.setup();
    renderPool(null);

    expect(screen.getByText("models.globalDefault")).toBeInTheDocument();

    // Clicking the global default's unlit star sets it as the personal
    // preference (set), it does not try to clear anything.
    await user.click(starButtonFor("prov-a / Model A"));
    await waitFor(() =>
      expect(preferencesApi.patch).toHaveBeenCalledWith({
        preferred_model: "prov-a/model-a",
      }),
    );
  });
});
