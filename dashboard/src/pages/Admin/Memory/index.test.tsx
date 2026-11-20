import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    getGlobalMemoryDefaults: vi.fn(),
    putGlobalMemoryDefaults: vi.fn(),
  },
}));

vi.mock("../../../api/modules/provider", () => ({
  providerApi: {
    listResolvedModels: vi.fn(),
  },
}));

vi.mock("../../../layouts/PageShell", () => ({
  default: ({
    title,
    subtitle,
    children,
  }: {
    title: string;
    subtitle?: string;
    children: React.ReactNode;
  }) => (
    <div>
      <h1>{title}</h1>
      {subtitle ? <p>{subtitle}</p> : null}
      {children}
    </div>
  ),
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import { providerApi } from "../../../api/modules/provider";
import AdminMemoryPage from "./index";

const api = vi.mocked(memoryDashboardApi, true);
const providers = vi.mocked(providerApi, true);

beforeEach(() => {
  vi.clearAllMocks();
  providers.listResolvedModels.mockResolvedValue([
    { provider_name: "hai", model: "mini", name: "Mini" },
  ] as never);
});

describe("<AdminMemoryPage />", () => {
  it("loads global memory defaults and saves model and keep/skip rules", async () => {
    api.getGlobalMemoryDefaults.mockResolvedValue({
      aux_model: null,
      aux_model_usable: true,
      extract_keep_rules: "",
      extract_skip_rules: "",
      supported_call_options: ["extract_rules"],
    });
    api.putGlobalMemoryDefaults.mockResolvedValue({
      aux_model: "hai/mini",
      aux_model_usable: true,
      extract_keep_rules: "保留稳定偏好与长期项目决策",
      extract_skip_rules: "跳过一次性问答与寒暄",
      supported_call_options: ["extract_rules"],
      affected_agent_count: 3,
    });

    const user = userEvent.setup();
    render(<AdminMemoryPage />);
    await screen.findByText("默认记忆提取模型");

    await user.click(
      screen.getByRole("combobox", { name: "默认记忆提取模型" }),
    );
    await user.click(await screen.findByTitle("hai / Mini"));

    await user.type(
      screen.getByLabelText("值得保留为长期记忆的信息"),
      "保留稳定偏好与长期项目决策",
    );
    await user.type(
      screen.getByLabelText("应当跳过的信息"),
      "跳过一次性问答与寒暄",
    );

    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putGlobalMemoryDefaults).toHaveBeenCalledWith({
        aux_model: "hai/mini",
        extract_keep_rules: "保留稳定偏好与长期项目决策",
        extract_skip_rules: "跳过一次性问答与寒暄",
      }),
    );
  });

  it("shows a warning when the saved global extraction model is unavailable", async () => {
    api.getGlobalMemoryDefaults.mockResolvedValue({
      aux_model: "deleted/old-mini",
      aux_model_usable: false,
      extract_keep_rules: "",
      extract_skip_rules: "",
      supported_call_options: ["extract_rules"],
    });

    render(<AdminMemoryPage />);
    await screen.findByText(/当前配置的全局提取模型不可用/);
  });
});

it("keeps saving unavailable after a failed load and retries the read", async () => {
  api.getGlobalMemoryDefaults
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({
      aux_model: null,
      extract_keep_rules: "existing preference",
      extract_skip_rules: "",
    });
  const user = userEvent.setup();
  render(<AdminMemoryPage />);
  await screen.findByText("全局记忆默认设置加载失败");
  expect(
    screen.queryByRole("button", { name: "保存设置" }),
  ).not.toBeInTheDocument();
  expect(api.putGlobalMemoryDefaults).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: /重\s*试/ }));
  expect(
    await screen.findByDisplayValue("existing preference"),
  ).toBeInTheDocument();
  expect(api.getGlobalMemoryDefaults).toHaveBeenCalledTimes(2);
});

it("saves only the changed rule when the configured model is unavailable", async () => {
  const defaults = {
    aux_model: "offline/lite",
    aux_model_usable: false,
    extract_keep_rules: "Keep",
    extract_skip_rules: "",
  };
  api.getGlobalMemoryDefaults.mockResolvedValue(defaults);
  api.putGlobalMemoryDefaults.mockResolvedValue({
    ...defaults,
    extract_skip_rules: "Skip",
  });
  const user = userEvent.setup();
  render(<AdminMemoryPage />);
  await user.type(await screen.findByLabelText("应当跳过的信息"), "Skip");
  await user.click(screen.getByRole("button", { name: "保存设置" }));
  expect(api.putGlobalMemoryDefaults).toHaveBeenCalledWith({
    extract_skip_rules: "Skip",
  });
  expect(screen.getByDisplayValue("Keep")).toBeInTheDocument();
});
