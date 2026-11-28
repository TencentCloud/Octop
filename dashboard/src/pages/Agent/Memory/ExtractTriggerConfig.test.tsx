import { MemoryRouter } from "react-router-dom";
import { CurrentUserProvider } from "../../../hooks/useCurrentUser";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    storageMaintenanceStatus: vi
      .fn()
      .mockResolvedValue({ busy: false, job: null }),
    checkStorage: vi.fn().mockRejectedValue(new Error("expert stopped")),
    getExtractConfig: vi.fn(),
    putExtractConfig: vi.fn(),
  },
}));

vi.mock("../../../api/modules/provider", () => ({
  providerApi: {
    listResolvedModels: vi.fn(),
  },
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import { providerApi } from "../../../api/modules/provider";
import MemorySettings from "./MemorySettings";

const api = vi.mocked(memoryDashboardApi, true);
const providers = vi.mocked(providerApi, true);

const idleConfig = {
  memory_enabled: true,
  extract_on_session_end: true,
  extract_trigger_mode: "idle" as const,
  extract_idle_seconds: 300,
  extract_interval_seconds: 21600,
};

beforeEach(() => {
  vi.clearAllMocks();
  providers.listResolvedModels.mockResolvedValue([]);
});

describe("<MemorySettings />", () => {
  it("loads the memory switch and distillation timing", async () => {
    api.getExtractConfig.mockResolvedValue(idleConfig);
    render(<MemorySettings agentId="ZYWZTD" />);

    await screen.findByText("存储记忆");
    expect(screen.getByText("已开启")).toBeInTheDocument();
    expect(screen.getByText("对话空闲后提炼")).toBeInTheDocument();
    expect(screen.getAllByRole("spinbutton")[0]).toHaveValue("5");
  });

  it("explains exactly what happens when memory is disabled", async () => {
    api.getExtractConfig.mockResolvedValue(idleConfig);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await screen.findByText("存储记忆");

    await user.click(screen.getByRole("switch"));
    expect(screen.getByText("关闭后 Agent 将不再使用记忆")).toBeInTheDocument();
    expect(
      screen.getByText(/已有记忆和对话记录不会被删除/),
    ).toBeInTheDocument();
  });

  it("saves the real memory switch and converted timing values", async () => {
    api.getExtractConfig.mockResolvedValue(idleConfig);
    api.putExtractConfig.mockResolvedValue(idleConfig);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await screen.findByText("存储记忆");

    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() => {
      expect(api.putExtractConfig).toHaveBeenCalledWith("ZYWZTD", {
        memory_enabled: true,
        extract_on_session_end: true,
        extract_trigger_mode: "idle",
        extract_idle_seconds: 300,
        extract_interval_seconds: 21600,
        aux_model_mode: "inherit",
        aux_model: null,
        extract_rules_mode: "inherit",
        extract_keep_rules: "",
        extract_skip_rules: "",
        extract_max_tokens: 0,
        extract_light_timeout_s: 0,
        extract_heavy_timeout_s: 0,
        extract_thinking: "auto",
        extract_max_retries: 2,
        extract_retry_backoff_s: 1,
        extract_extra_body: {},
      });
    });
  });

  it("switches extraction model to custom and saves a pinned model", async () => {
    api.getExtractConfig.mockResolvedValue({
      ...idleConfig,
      global_defaults: {
        aux_model: "hai/global-light",
        aux_model_usable: true,
        extract_keep_rules: "保留稳定偏好",
        extract_skip_rules: "跳过寒暄",
      },
    });
    api.putExtractConfig.mockResolvedValue({
      ...idleConfig,
      aux_model_mode: "custom",
      aux_model: "hai/mini",
    });
    providers.listResolvedModels.mockResolvedValue([
      { provider_name: "hai", model: "mini", name: "Mini" },
    ] as never);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await screen.findByText("记忆提取模型");
    expect(
      screen.getByText(/当前继承全局：hai\/global-light/),
    ).toBeInTheDocument();

    // Switch extraction model to custom while leaving memory rules inherited.
    const customButtons = screen.getAllByText("自定义");
    await user.click(customButtons[0]);
    await user.click(screen.getByRole("combobox", { name: "记忆提取模型" }));
    await user.click(await screen.findByTitle("hai / Mini"));
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({
          aux_model_mode: "custom",
          aux_model: "hai/mini",
          extract_rules_mode: "inherit",
        }),
      ),
    );
  });

  it("prefills global rules when switching to custom and supports restoring inheritance", async () => {
    api.getExtractConfig.mockResolvedValue({
      ...idleConfig,
      supported_call_options: ["extract_rules"],
      global_defaults: {
        aux_model: "hai/global-light",
        aux_model_usable: true,
        extract_keep_rules: "全局保留偏好",
        extract_skip_rules: "全局跳过闲聊",
      },
    });
    api.putExtractConfig.mockResolvedValue({
      ...idleConfig,
      extract_rules_mode: "custom",
      extract_keep_rules: "全局保留偏好 + 领域记录",
      extract_skip_rules: "全局跳过闲聊",
    });
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await screen.findByText("记忆规则");
    expect(screen.getByText("全局保留偏好")).toBeInTheDocument();
    expect(screen.getByText("全局跳过闲聊")).toBeInTheDocument();

    const customButtons = screen.getAllByText("自定义");
    await user.click(customButtons[1]);

    const keepInput = screen.getByLabelText("值得保留为长期记忆的信息");
    expect(keepInput).toHaveValue("全局保留偏好");
    await user.type(keepInput, " + 领域记录");

    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({
          aux_model_mode: "inherit",
          extract_rules_mode: "custom",
          extract_keep_rules: "全局保留偏好 + 领域记录",
          extract_skip_rules: "全局跳过闲聊",
        }),
      ),
    );

    // Restore inheritance on rules.
    await user.click(screen.getByRole("button", { name: "恢复继承全局" }));
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenLastCalledWith(
        "ZYWZTD",
        expect.objectContaining({
          extract_rules_mode: "inherit",
          extract_keep_rules: "",
          extract_skip_rules: "",
        }),
      ),
    );
  });

  it("normalizes an invalid zero idle time to one minute", async () => {
    api.getExtractConfig.mockResolvedValue({
      ...idleConfig,
      extract_idle_seconds: 0,
    });
    api.putExtractConfig.mockResolvedValue({
      ...idleConfig,
      extract_idle_seconds: 60,
    });
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);

    await screen.findByText("存储记忆");
    expect(screen.getAllByRole("spinbutton")[0]).toHaveValue("1");
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({ extract_idle_seconds: 60 }),
      ),
    );
  });

  it("loads and saves the advanced distillation call limits", async () => {
    api.getExtractConfig.mockResolvedValue({
      ...idleConfig,
      extract_max_tokens: 1024,
      extract_light_timeout_s: 45,
      extract_heavy_timeout_s: null,
    });
    api.putExtractConfig.mockResolvedValue(idleConfig);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);

    await screen.findByText("记忆高级设置");
    expect(
      screen.queryByRole("spinbutton", { name: "单次提炼最多生成" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByText("记忆高级设置"));
    const spinbuttons = screen.getAllByRole("spinbutton");
    expect(spinbuttons).toHaveLength(6);
    // Stored values render as-is; null renders as the automatic sentinel.
    expect(spinbuttons[1]).toHaveValue("1024");
    expect(spinbuttons[2]).toHaveValue("45");
    expect(spinbuttons[3]).toHaveValue("0");
    expect(
      screen.getByText(/重试和模型回退可能延长总耗时/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({
          extract_max_tokens: 1024,
          extract_light_timeout_s: 45,
          extract_heavy_timeout_s: 0,
        }),
      ),
    );
  });

  it("shows the interval caveat", async () => {
    api.getExtractConfig.mockResolvedValue(idleConfig);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await screen.findByText("固定间隔提炼");
    await user.click(screen.getByText("固定间隔提炼"));
    expect(await screen.findByText(/会话尚未结束时运行/)).toBeInTheDocument();
  });
  it("edits and persists thinking, retries, and model-specific parameters", async () => {
    api.getExtractConfig.mockResolvedValue({
      ...idleConfig,
      extract_thinking: "off",
      extract_max_retries: 0,
      extract_retry_backoff_s: 0.5,
      extract_extra_body: { reasoning_effort: "low" },
    });
    api.putExtractConfig.mockResolvedValue(idleConfig);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await user.click(await screen.findByText("记忆高级设置"));
    expect(
      screen.getByRole("spinbutton", { name: "失败重试次数" }),
    ).toHaveValue("0");
    expect(
      screen.getByRole("spinbutton", { name: "首次重试间隔" }),
    ).toHaveValue("0.5");
    await user.click(screen.getByText("高级模型参数（JSON）"));
    expect(
      screen.getByRole("textbox", { name: "高级模型参数（JSON）" }),
    ).toHaveValue(JSON.stringify({ reasoning_effort: "low" }, null, 2));
    await user.click(screen.getByRole("combobox", { name: "提炼思考模式" }));
    await user.click(await screen.findByTitle("沿用模型默认"));
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({
          extract_thinking: "on",
          extract_max_retries: 0,
          extract_retry_backoff_s: 0.5,
          extract_extra_body: { reasoning_effort: "low" },
        }),
      ),
    );
  });

  it("rejects invalid advanced JSON and lets the user clear it", async () => {
    api.getExtractConfig.mockResolvedValue(idleConfig);
    api.putExtractConfig.mockResolvedValue(idleConfig);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await user.click(await screen.findByText("记忆高级设置"));
    await user.click(await screen.findByText("高级模型参数（JSON）"));
    const input = screen.getByRole("textbox", { name: "高级模型参数（JSON）" });
    await user.type(input, "null");
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    expect(api.putExtractConfig).not.toHaveBeenCalled();
    expect(
      screen.getAllByText("模型扩展参数必须是有效的 JSON 对象").length,
    ).toBeGreaterThan(0);
    await user.clear(input);
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({ extract_extra_body: {} }),
      ),
    );
  });

  it("explains and disables unavailable options on an older runtime", async () => {
    api.getExtractConfig.mockResolvedValue({
      ...idleConfig,
      supported_call_options: [
        "extract_max_tokens",
        "extract_light_timeout_s",
        "extract_heavy_timeout_s",
        "extract_thinking",
      ],
    });
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await user.click(await screen.findByText("记忆高级设置"));
    expect(
      await screen.findByText("当前版本尚不支持全部调用设置"),
    ).toBeVisible();
    expect(
      screen.getByRole("spinbutton", { name: "失败重试次数" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("spinbutton", { name: "单次提炼最多生成" }),
    ).toBeEnabled();
  });
});

it("keeps global management links under the dashboard deployment prefix", async () => {
  api.getExtractConfig.mockResolvedValue(idleConfig);
  render(
    <MemoryRouter basename="/octop" initialEntries={["/octop/experts"]}>
      <CurrentUserProvider
        user={{
          id: 1,
          username: "admin",
          role: "admin",
          display_name: null,
          locale: "zh",
        }}
        setUser={vi.fn()}
      >
        <MemorySettings agentId="ZYWZTD" />
      </CurrentUserProvider>
    </MemoryRouter>,
  );
  const links = await screen.findAllByRole("link", { name: "管理全局默认" });
  expect(links).toHaveLength(2);
  for (const link of links)
    expect(link).toHaveAttribute("href", "/octop/admin/memory");
});
