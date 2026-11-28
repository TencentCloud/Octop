import { Form } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, it, expect, vi } from "vitest";
import { providerApi } from "../api/modules/provider";
import { GlobalCompactModel, ExpertCompactModel } from "./CompactModelSelect";
import { buildAgentRuntimeRequest } from "../utils/agentRuntimeConfig";

vi.mock("../api/modules/provider", () => ({
  providerApi: { getCompactionModel: vi.fn(), setCompactionModel: vi.fn() },
}));
const models = [{ provider_name: "provider", model: "small", name: "Small" }];
beforeEach(() => {
  vi.clearAllMocks();
});
it("saves a global summary model and clears it back to the current conversation", async () => {
  const user = userEvent.setup();
  vi.mocked(providerApi.getCompactionModel).mockResolvedValue({ model: null });
  vi.mocked(providerApi.setCompactionModel).mockImplementation(
    async (model) => ({ model }),
  );
  render(<GlobalCompactModel models={models} />);
  const picker = screen.getByRole("combobox");
  await waitFor(() => expect(picker).not.toBeDisabled());
  await user.click(picker);
  await user.click(screen.getByText("provider / Small"));
  await waitFor(() =>
    expect(providerApi.setCompactionModel).toHaveBeenCalledWith(
      "provider/small",
    ),
  );
  await user.click(picker);
  await user.click(
    screen.getByText("Follow the current conversation", {
      selector: ".ant-select-item-option-content",
    }),
  );
  await waitFor(() =>
    expect(providerApi.setCompactionModel).toHaveBeenLastCalledWith(null),
  );
});
it("shows the inherited global model and can override it to follow the conversation with automatic compaction off", async () => {
  const user = userEvent.setup();
  vi.mocked(providerApi.getCompactionModel).mockResolvedValue({
    model: "provider/small",
  });
  const submit = vi.fn();
  render(
    <Form
      initialValues={{ compaction: { enabled: false } }}
      onFinish={(v) =>
        submit(buildAgentRuntimeRequest(v, { clearMissing: true }))
      }
    >
      <Form.Item hidden name={["compaction", "enabled"]}>
        <input />
      </Form.Item>
      <ExpertCompactModel models={models} />
      <button type="submit">save</button>
    </Form>,
  );
  await screen.findByText(/provider\/small/);
  await user.click(screen.getByRole("combobox"));
  await user.click(
    screen.getByText("Follow the current conversation", {
      selector: ".ant-select-item-option-content",
    }),
  );
  await user.click(screen.getByText("save"));
  await waitFor(() =>
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        compaction: expect.objectContaining({
          model: "session",
          enabled: false,
        }),
      }),
    ),
  );
});
