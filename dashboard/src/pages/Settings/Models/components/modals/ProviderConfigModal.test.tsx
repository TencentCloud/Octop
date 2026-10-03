import { App } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { request } from "../../../../../api/request";
import { ProviderConfigModal } from "./ProviderConfigModal";
import type { ProviderRow } from "../../useProviders";

vi.mock("../../../../../api/request", () => ({ request: vi.fn() }));
vi.mock("./ModelListEditor", () => ({ ModelListEditor: () => null }));

const provider: ProviderRow = {
  id: 12,
  name: "custom",
  kind: "openai",
  base_url: "https://example.com/v1",
  api_key: "test-key",
  model: "chosen-third",
  models: [
    { id: "disabled-first", name: "disabled-first", enabled: false },
    { id: "enabled-second", name: "enabled-second", enabled: true },
    { id: "chosen-third", name: "chosen-third", enabled: true },
  ],
  note: null,
  enabled: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(request).mockResolvedValue({
    ...provider,
    model: "enabled-second",
  });
});

it("loads the saved default and submits a changed model without changing the model list", async () => {
  const user = userEvent.setup();
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
  await screen.findByTitle("chosen-third");
  await user.click(
    screen.getByRole("combobox", { name: "models.defaultModelLabel" }),
  );
  await user.click(await screen.findByTitle("enabled-second"));
  await user.click(screen.getByRole("button", { name: "common.save" }));
  await waitFor(() => expect(request).toHaveBeenCalled());
  const [, options] = vi.mocked(request).mock.calls[0];
  expect(JSON.parse(options!.body as string)).toEqual({
    model: "enabled-second",
  });
});

it("keeps automatic probe selection blank when no default is stored", async () => {
  render(
    <App>
      <ProviderConfigModal
        provider={{ ...provider, model: null }}
        open
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    </App>,
  );
  await screen.findByRole("combobox", { name: "models.defaultModelLabel" });
  expect(screen.queryByTitle("disabled-first")).not.toBeInTheDocument();
});
