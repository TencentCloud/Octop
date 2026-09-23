import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoadingPage from "./LoadingPage";
import SettingsPage from "./SettingsPage";
import { isStuckStatus, statusFromEvent } from "./wails";

describe("desktop shell", () => {
  it("renders loading progress and status at the bottom of the card", () => {
    render(<LoadingPage status="Starting Octop…" stuck={false} />);
    const card = screen.getByTestId("loading-card");
    const footer = screen.getByTestId("loading-footer");
    const bar = screen.getByTestId("loading-bar");
    const status = screen.getByTestId("status");
    expect(card.contains(footer)).toBe(true);
    expect(footer.contains(bar)).toBe(true);
    expect(footer.contains(status)).toBe(true);
    expect(screen.getByTestId("mascot")).toBeInTheDocument();
    expect(screen.getByTestId("loading-brand")).toHaveTextContent("Octop");
    expect(screen.queryByRole("progressbar", { hidden: true })).toBeTruthy();
  });

  it("marks the loading panel when startup is stuck", () => {
    render(<LoadingPage status="Could not connect" stuck />);
    expect(screen.getByTestId("loading-panel")).toHaveAttribute(
      "data-stuck",
      "1",
    );
  });

  it("saves settings toggles through onChange", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SettingsPage
        value={{
          locale: "en",
          autostart: false,
          minimizeToTray: true,
          preventSleep: false,
        }}
        error=""
        onChange={onChange}
        onShowMain={vi.fn()}
        onQuit={vi.fn()}
      />,
    );
    expect(screen.getByTestId("settings-panel")).toBeInTheDocument();
    await user.click(screen.getAllByRole("checkbox")[0]);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ autostart: true }),
    );
  });

  it("detects stuck backend status copy", () => {
    expect(isStuckStatus("Octop did not become ready within 1 minute")).toBe(
      true,
    );
    expect(isStuckStatus("正在启动 Octop 服务…")).toBe(false);
  });

  it("reads the error flag from desktop:status events", () => {
    expect(statusFromEvent("Connecting to Octop…")).toEqual({
      text: "Connecting to Octop…",
      error: false,
    });
    expect(statusFromEvent({ data: "Connecting to Octop…" })).toEqual({
      text: "Connecting to Octop…",
      error: false,
    });
    expect(
      statusFromEvent({
        data: { message: "端口 8088 已被占用", error: true },
      }),
    ).toEqual({ text: "端口 8088 已被占用", error: true });
    expect(statusFromEvent({ data: { message: "Octop is ready" } })).toEqual({
      text: "Octop is ready",
      error: false,
    });
  });
});
