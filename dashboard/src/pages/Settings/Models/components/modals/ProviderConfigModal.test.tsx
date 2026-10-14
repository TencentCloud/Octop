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

describe("ProviderConfigModal", () => {
  it("opens with an empty test model even when the provider has models", async () => {
    const provider: ProviderRow = {
      id: 1,
      name: "custom",
      kind: "openai",
      base_url: null,
      api_key: null,
      models: [{ id: "first-model", name: "First model", enabled: true }],
      note: null,
      enabled: true,
    };

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

    const field = (await screen.findByText("models.defaultModelLabel")).closest(
      ".ant-form-item",
    );
    expect(field).not.toBeNull();
    expect(within(field!).queryByText("First model")).not.toBeInTheDocument();
    expect(within(field!).getByRole("combobox")).toHaveValue("");
  });
});
