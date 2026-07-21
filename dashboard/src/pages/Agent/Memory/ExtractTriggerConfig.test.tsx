import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
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
    expect(screen.getByRole("spinbutton")).toHaveValue("5");
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
        aux_model: "",
      });
    });
  });

  it("saves a pinned extraction model", async () => {
    api.getExtractConfig.mockResolvedValue(idleConfig);
    api.putExtractConfig.mockResolvedValue({
      ...idleConfig,
      aux_model: "hai/mini",
    });
    providers.listResolvedModels.mockResolvedValue([
      { provider_name: "hai", model: "mini", name: "Mini" },
    ] as never);
    const user = userEvent.setup();
    render(<MemorySettings agentId="ZYWZTD" />);
    await screen.findByText("记忆提取模型");

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByTitle("hai / Mini"));
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({ aux_model: "hai/mini" }),
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
    expect(screen.getByRole("spinbutton")).toHaveValue("1");
    await user.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() =>
      expect(api.putExtractConfig).toHaveBeenCalledWith(
        "ZYWZTD",
        expect.objectContaining({ extract_idle_seconds: 60 }),
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
});
