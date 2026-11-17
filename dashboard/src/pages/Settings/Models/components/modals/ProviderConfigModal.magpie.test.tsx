import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { App } from "antd";
import { beforeEach, expect, it, vi } from "vitest";
import { ProviderConfigModal } from "./ProviderConfigModal";

const fetchModels = vi.fn();
const request = vi.fn();
vi.mock("../../providerApi", () => ({
  fetchProviderModels: (...args: unknown[]) => fetchModels(...args),
  testProviderDraft: vi.fn(),
}));
vi.mock("../../../../../api/request", () => ({
  request: (...args: unknown[]) => request(...args),
}));

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({});
});

it("saves the fetched connection snapshot and keeps later edits dirty", async () => {
  let finishFetch!: (value: unknown) => void;
  fetchModels.mockImplementation(
    () =>
      new Promise((resolve) => {
        finishFetch = resolve;
      }),
  );
  const onSaved = vi.fn();
  render(
    <App>
      <ProviderConfigModal
        provider={{
          id: 1,
          name: "Magpie",
          kind: "openai",
          base_url: "http://127.0.0.1:3425/v1",
          api_key: "magpie-octop",
          note: null,
          enabled: true,
          models: [{ id: "old", name: "Old", enabled: true }],
        }}
        open
        apiPrefix="/admin/providers"
        onClose={vi.fn()}
        onSaved={onSaved}
      />
    </App>,
  );
  const address = screen.getByLabelText("Base URL");
  fireEvent.change(address, { target: { value: "https://first.example/v1" } });
  fireEvent.click(screen.getByRole("button", { name: "models.magpieRefresh" }));
  await waitFor(() => expect(fetchModels).toHaveBeenCalled());
  fireEvent.change(address, { target: { value: "https://second.example/v1" } });
  await act(async () =>
    finishFetch({ ok: true, models: [{ id: "new", name: "New" }] }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "common.confirm" }),
  );
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  const payload = JSON.parse(request.mock.calls[0][1].body);
  expect(payload.base_url).toBe("https://first.example/v1");
  expect(payload.models.map((model: { id: string }) => model.id)).toEqual([
    "new",
  ]);
  expect(screen.getByRole("button", { name: "common.save" })).toBeEnabled();
});
