import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  connectorsApi,
  type AgentlyAuthStatus,
} from "../../../api/modules/connectors";
import { AgentlyAuth } from "./AgentlyAuth";

const status = (value: AgentlyAuthStatus["status"]): AgentlyAuthStatus => ({
  status: value,
  verification_url:
    value === "pending" ? "https://mail.example/authorize" : null,
  user_code: value === "pending" ? "MAIL-1234" : null,
  expires_at: null,
  error: null,
});

describe("AgentlyAuth", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("authorizes the saved instance, polls, then refreshes and logs out", async () => {
    let current = status("idle");
    const api = vi
      .spyOn(connectorsApi, "agentlyAuth")
      .mockImplementation(async (_id, action) => {
        if (action === "start") current = status("pending");
        if (action === "logout") current = status("idle");
        return current;
      });
    const onChanged = vi.fn();
    await act(async () => {
      render(
        <AgentlyAuth instanceId="mail-a" installed onChanged={onChanged} />,
      );
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "登录授权" }));
    });
    expect(api).toHaveBeenCalledWith("mail-a", "start");
    expect(screen.getByRole("link", { name: "打开授权页" })).toHaveAttribute(
      "href",
      "https://mail.example/authorize",
    );
    expect(screen.getByText("MAIL-1234")).toBeInTheDocument();
    current = status("authorized");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.getByText("邮箱已授权")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(2);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "刷新授权" }));
    });
    expect(api).toHaveBeenCalledWith("mail-a", "refresh");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "注销授权" }));
    });
    expect(api).toHaveBeenCalledWith("mail-a", "logout");
    expect(screen.getByText("尚未授权此邮箱实例")).toBeInTheDocument();
  });

  it("stops polling when closed and restores pending authorization on reopen", async () => {
    const api = vi
      .spyOn(connectorsApi, "agentlyAuth")
      .mockResolvedValue(status("pending"));
    let view: ReturnType<typeof render>;
    await act(async () => {
      view = render(
        <AgentlyAuth instanceId="mail-b" installed onChanged={vi.fn()} />,
      );
    });
    view!.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(api).toHaveBeenCalledTimes(1);
    await act(async () => {
      render(<AgentlyAuth instanceId="mail-b" installed onChanged={vi.fn()} />);
    });
    expect(api).toHaveBeenCalledTimes(2);
    expect(screen.getByText("MAIL-1234")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(api).toHaveBeenCalledTimes(3);
  });

  it("keeps action failures visible and requires an installed CLI to authorize", async () => {
    const api = vi
      .spyOn(connectorsApi, "agentlyAuth")
      .mockResolvedValue(status("idle"));
    let view: ReturnType<typeof render>;
    await act(async () => {
      view = render(
        <AgentlyAuth
          instanceId="mail-c"
          installed={false}
          onChanged={vi.fn()}
        />,
      );
    });
    expect(screen.getByRole("button", { name: "登录授权" })).toBeDisabled();
    view!.rerender(
      <AgentlyAuth instanceId="mail-c" installed onChanged={vi.fn()} />,
    );
    api.mockRejectedValueOnce(new Error("Authorization unavailable"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "登录授权" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Authorization unavailable",
    );
    expect(screen.getByRole("button", { name: "登录授权" })).toBeEnabled();
  });
});
