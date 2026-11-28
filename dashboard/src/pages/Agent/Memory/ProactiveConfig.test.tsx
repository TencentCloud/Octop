import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import api from "../../../api";
import { providerApi } from "../../../api/modules/provider";
import ProactiveConfig from "./ProactiveConfig";

vi.mock("../../../api", () => ({
  default: {
    getProactiveCareConfig: vi.fn(),
    updateProactiveCareConfig: vi.fn(),
  },
}));
vi.mock("../../../api/modules/provider", () => ({
  providerApi: { listResolvedModels: vi.fn() },
}));

it("loads an inherited care model and saves a supported effort and timeout for a different model", async () => {
  const user = userEvent.setup();
  vi.mocked(api.getProactiveCareConfig).mockResolvedValue({
    enabled: true,
    active_hours_start: "09:00",
    active_hours_end: "22:00",
    min_interval_hours: 5,
    max_interval_hours: 24,
    default_model_ref: "demo/main",
    model_ref: null,
    reasoning_effort: "disabled",
    generation_timeout_seconds: 45,
  });
  vi.mocked(providerApi.listResolvedModels).mockResolvedValue(
    ["main", "fast"].map((model) => ({
      provider_id: 1,
      provider_name: "demo",
      provider_kind: "openai",
      model,
      name: model,
      reasoning_config: {
        supported: true,
        toggle: model === "main",
        default_mode: "auto",
        efforts: model === "fast" ? ["low", "high"] : [],
        effort_type: "enum",
        adapter: "openai_reasoning_effort",
      },
    })),
  );
  render(<ProactiveConfig agentId="expert" />);
  const timeout = await screen.findByLabelText(
    "proactiveConfig.generationTimeout",
  );
  expect(timeout).toHaveValue("45");
  expect(
    screen.getByText("proactiveConfig.disableThinking"),
  ).toBeInTheDocument();
  await user.click(screen.getByLabelText("proactiveConfig.generationModel"));
  await user.click(await screen.findByTitle("demo / fast"));
  expect(screen.getByText("proactiveConfig.modelDefault")).toBeInTheDocument();
  await user.click(screen.getByLabelText("proactiveConfig.reasoningEffort"));
  await user.click(await screen.findByTitle("low"));
  await user.clear(timeout);
  await user.type(timeout, "90");
  await user.click(screen.getByRole("button", { name: /保\s*存/ }));
  await waitFor(() =>
    expect(api.updateProactiveCareConfig).toHaveBeenCalledWith("expert", {
      enabled: true,
      active_hours_start: "09:00",
      active_hours_end: "22:00",
      min_interval_hours: 5,
      max_interval_hours: 24,
      model_ref: "demo/fast",
      reasoning_effort: "low",
      generation_timeout_seconds: 90,
    }),
  );
});
