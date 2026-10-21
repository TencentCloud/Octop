import { render, screen, within } from "@testing-library/react";
import { App } from "antd";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import type { ProviderRow } from "../../useProviders";
import { ProviderConfigModal } from "./ProviderConfigModal";

const getComputedStyle = window.getComputedStyle;

beforeAll(() => {
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    getComputedStyle(element),
  );
});

afterAll(() => {
  vi.restoreAllMocks();
});

function providerRow(overrides: Partial<ProviderRow> = {}): ProviderRow {
  return {
    id: 1,
    name: "custom",
    kind: "openai",
    base_url: null,
    api_key: null,
    models: [
      { id: "first-model", name: "First model", enabled: true },
      { id: "second-model", name: "Second model", enabled: true },
    ],
    note: null,
    enabled: true,
    ...overrides,
  };
}

function renderModal(provider: ProviderRow) {
  render(
    <App>
      <ProviderConfigModal
        provider={provider}
        open
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    </App>,
  );
}

async function defaultModelField() {
  const label = await screen.findByText("models.defaultModelLabel");
  return label.closest(".ant-form-item") as HTMLElement;
}

describe("ProviderConfigModal", () => {
  it("shows the saved default model", async () => {
    renderModal(providerRow({ default_model: "second-model" }));

    const field = await defaultModelField();

    expect(
      await within(field).findByText("Second model (second-model)"),
    ).toBeInTheDocument();
  });

  it("opens empty when no default was ever saved", async () => {
    renderModal(providerRow());

    const field = await defaultModelField();

    expect(
      within(field).queryByText("First model (first-model)"),
    ).not.toBeInTheDocument();
    expect(await within(field).findByRole("combobox")).toHaveValue("");
  });

  it("opens empty after the default was cleared", async () => {
    renderModal(providerRow({ default_model: null }));

    const field = await defaultModelField();

    expect(
      within(field).queryByText("First model (first-model)"),
    ).not.toBeInTheDocument();
    expect(await within(field).findByRole("combobox")).toHaveValue("");
  });
});
