import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoadingPage from "./LoadingPage";
import SettingsPage from "./SettingsPage";
import { statusFromEvent } from "./wails";

describe("desktop shell", () => {
  it("renders loading progress and status at the bottom of the card", () => {
    render(
      <LoadingPage
        status={{
          code: "status.connecting",
          level: "progress",
          args: {},
        }}
      />,
    );
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
    render(
      <LoadingPage
        status={{
          code: "health.not_ready_connect",
          level: "error",
          args: { addr: "http://127.0.0.1:8088", seconds: 60 },
        }}
      />,
    );
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

  it("reads code, level and args from desktop:status events", () => {
    expect(
      statusFromEvent({
        data: {
          code: "error.port_in_use",
          level: "error",
          args: { port: 8088 },
        },
      }),
    ).toEqual({
      code: "error.port_in_use",
      level: "error",
      args: { port: 8088 },
    });
    expect(
      statusFromEvent({
        data: { code: "status.ready", level: "progress" },
      }),
    ).toEqual({
      code: "status.ready",
      level: "progress",
      args: {},
    });
    expect(statusFromEvent({ data: {} })).toEqual({
      code: "",
      level: "progress",
      args: {},
    });
  });
});
