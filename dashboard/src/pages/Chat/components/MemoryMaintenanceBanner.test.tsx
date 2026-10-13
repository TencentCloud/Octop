import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import zh from "../../../locales/zh.json";
import MemoryMaintenanceBanner from "./MemoryMaintenanceBanner";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const strings = zh.chat.memoryMaintenance as Record<string, string>;
      const text = strings[key.replace("chat.memoryMaintenance.", "")] ?? key;
      return text.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
        String(options?.[name] ?? ""),
      );
    },
  }),
}));

afterEach(() => vi.useRealTimers());

describe("MemoryMaintenanceBanner", () => {
  it("explains a long pause and points users to another agent without inventing an ETA", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-18T00:00:00Z"));
    render(
      <MemoryMaintenanceBanner
        status={{ phase: "compacting", started_at: Date.now() / 1000 }}
        blocking
      />,
    );
    expect(screen.getByText(/此智能体的所有会话/)).toBeInTheDocument();
    expect(screen.queryByText(/无法可靠预估剩余时间/)).not.toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(61000);
    });
    expect(screen.getByText(/无法可靠预估剩余时间/)).toBeInTheDocument();
    expect(screen.getByText("已进行 61s")).toBeInTheDocument();
  });

  it.each(["done", "failed", "skipped"])(
    "makes %s visible and dismissible without a running spinner",
    (phase) => {
      const { container, rerender } = render(
        <MemoryMaintenanceBanner
          status={{ phase, started_at: 10, updated_at: 20 }}
          blocking={false}
        />,
      );
      expect(container.querySelector(".ant-spin")).toBeNull();
      expect(screen.getByText("已进行 10s")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "知道了" }));
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
      rerender(
        <MemoryMaintenanceBanner
          status={{ phase, started_at: 30, updated_at: 35 }}
          blocking={false}
        />,
      );
      expect(screen.getByRole("status")).toBeInTheDocument();
    },
  );

  it("distinguishes a lost connection from confirmed progress", () => {
    render(
      <MemoryMaintenanceBanner
        status={{ phase: "compacting" }}
        blocking
        connectionLost
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("信息可能已过时");
  });
});
