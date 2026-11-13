import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MagpieDiscoveryCard } from "./MagpieDiscoveryCard";
import type { ProviderRow } from "../useProviders";

const fetchProviderModels = vi.fn();
const request = vi.fn();

vi.mock("../providerApi", () => ({
  fetchProviderModels: (...args: unknown[]) => fetchProviderModels(...args),
}));

vi.mock("../../../../api/request", () => ({
  request: (...args: unknown[]) => request(...args),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    warning: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
  },
}));

function renderCard(
  discovery: {
    available: boolean;
    base_url: string;
    version: string | null;
  } | null,
  providers: ProviderRow[] = [],
) {
  const onRescan = vi.fn();
  const onAdded = vi.fn();
  render(
    <App>
      <MagpieDiscoveryCard
        discovery={discovery}
        scanning={false}
        providers={providers}
        onRescan={onRescan}
        onAdded={onAdded}
      />
    </App>,
  );
  return { onRescan, onAdded };
}

describe("MagpieDiscoveryCard", () => {
  beforeEach(() => {
    fetchProviderModels.mockReset();
    request.mockReset();
  });

  it("shows a miss without a blocking error and can rescan", async () => {
    const user = userEvent.setup();
    const { onRescan } = renderCard({
      available: false,
      base_url: "http://127.0.0.1:3425/v1",
      version: null,
    });
    expect(
      screen.getByText("models.magpieDiscoveryMissing"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "models.magpieAdd" }),
    ).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "models.magpieRescan" }),
    );
    expect(onRescan).toHaveBeenCalledOnce();
  });

  it("does not create a provider when the catalog is empty", async () => {
    const user = userEvent.setup();
    fetchProviderModels.mockResolvedValue({ ok: true, models: [] });
    renderCard({
      available: true,
      base_url: "http://127.0.0.1:3425/v1",
      version: "1.0.0",
    });
    await user.click(screen.getByRole("button", { name: "models.magpieAdd" }));
    expect(request).not.toHaveBeenCalled();
  });

  it("creates Magpie once and keeps the configuration panel open", async () => {
    const user = userEvent.setup();
    let resolveFetch: (value: unknown) => void = () => undefined;
    fetchProviderModels.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );
    request.mockResolvedValue({
      id: 7,
      name: "Magpie",
      kind: "openai",
      base_url: "http://127.0.0.1:3425/v1",
      api_key: "magpie-octop",
      models: [{ id: "group/a", name: "A", enabled: true }],
      note: null,
      enabled: true,
      integration: "magpie",
    });
    const { onAdded } = renderCard({
      available: true,
      base_url: "http://127.0.0.1:3425/v1",
      version: "1.2.0",
    });
    const button = screen.getByRole("button", { name: "models.magpieAdd" });
    await user.click(button);
    await user.click(button);
    expect(fetchProviderModels).toHaveBeenCalledOnce();
    resolveFetch({
      ok: true,
      models: [{ id: "vendor/org/model", name: "Shown" }],
    });
    expect(await screen.findByText("models.manageModels")).toBeInTheDocument();
    expect(request).toHaveBeenCalledOnce();
    expect(onAdded).toHaveBeenCalled();
  });

  it("does not offer add when Magpie is already configured", () => {
    renderCard(
      {
        available: true,
        base_url: "http://127.0.0.1:3425/v1",
        version: "1.0.0",
      },
      [
        {
          id: 3,
          name: "Magpie",
          kind: "openai",
          base_url: "http://127.0.0.1:3425/v1",
          api_key: "magpie-octop",
          models: [],
          note: null,
          enabled: true,
          integration: "magpie",
        },
      ],
    );
    expect(
      screen.queryByRole("button", { name: "models.magpieAdd" }),
    ).toBeNull();
    expect(screen.getByText("models.magpieAlreadyAdded")).toBeInTheDocument();
  });
});
