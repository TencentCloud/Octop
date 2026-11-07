import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DesktopUpdatePanel from "./DesktopUpdatePanel";

const installUpdate = vi.fn(() => Promise.resolve());

beforeEach(() => {
  installUpdate.mockClear();
  window.octopDesktop = {
    getPlatformInfo: vi.fn(),
    openDirectoryPicker: vi.fn(),
    openFilePicker: vi.fn(),
    onBackendReady: () => () => {},
    setWindowChrome: () => {},
    clientSettings: {
      get: vi.fn().mockResolvedValue({
        launchAtLogin: false,
        closeBehavior: "quit",
        themeBackground: "system",
        stableOnly: true,
      }),
      set: vi.fn(),
    },
    session: {
      register: vi.fn(),
      renew: vi.fn(),
      revoke: vi.fn(),
    },
    checkForUpdates: vi.fn().mockResolvedValue({
      status: "update-available",
      currentVersion: "1.0.3b1",
      latestVersion: "v1.0.4",
      error: null,
    }),
    installUpdate,
  };
});

afterEach(() => {
  delete window.octopDesktop;
});

describe("<DesktopUpdatePanel />", () => {
  it("confirms in the page and only then asks the shell to install", async () => {
    const user = userEvent.setup();
    render(<DesktopUpdatePanel />);

    expect(await screen.findByText("v1.0.4")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "advancedSettings.update.deviceLoginButton",
      }),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "advancedSettings.update.upgradeButton",
      }),
    );

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(
      "advancedSettings.update.shellConfirmTitle",
    );
    expect(dialog).toHaveTextContent(
      "advancedSettings.update.shellConfirmBody",
    );
    expect(installUpdate).not.toHaveBeenCalled();

    await user.click(
      within(dialog).getByRole("button", {
        name: "advancedSettings.update.later",
      }),
    );
    expect(installUpdate).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", {
        name: "advancedSettings.update.upgradeButton",
      }),
    );
    const again = await screen.findByRole("dialog");
    await user.click(
      within(again).getByRole("button", {
        name: "advancedSettings.update.upgradeButton",
      }),
    );
    expect(installUpdate).toHaveBeenCalledOnce();
    expect(installUpdate).toHaveBeenCalledWith();
  });
});
