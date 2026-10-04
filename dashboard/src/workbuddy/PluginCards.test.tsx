import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  InstalledPluginTile,
  MarketPluginTile,
} from "../pages/Admin/Plugins/WorkBuddyPluginCards";

describe("WorkBuddy plugin bindings", () => {
  it("forwards enable without opening details and keeps runtime errors visible", async () => {
    const onOpen = vi.fn(),
      onToggle = vi.fn();
    const { rerender } = render(
      <InstalledPluginTile
        plugin={{ id: "notes", name: "Notes", enabled: false, loaded: false }}
        toggling={false}
        onOpen={onOpen}
        onToggle={onToggle}
        onUninstall={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("switch"));
    expect(onToggle.mock.calls[0][0]).toBe(true);
    expect(onOpen).not.toHaveBeenCalled();
    rerender(
      <InstalledPluginTile
        plugin={{
          id: "notes",
          name: "Notes",
          error: "Missing dependency",
          enabled: true,
        }}
        toggling={false}
        onOpen={onOpen}
        onToggle={onToggle}
        onUninstall={vi.fn()}
      />,
    );
    expect(screen.getByText("Missing dependency")).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Notes" }));
    expect(onOpen).toHaveBeenCalledOnce();
  });
  it("uses force only for an available update and disables installed entries", async () => {
    const onInstall = vi.fn();
    const { rerender } = render(
      <MarketPluginTile
        plugin={{ id: "notes", installed: false }}
        installing={false}
        onInstall={onInstall}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "plugins.marketInstall" }),
    );
    expect(onInstall).toHaveBeenLastCalledWith(false);
    rerender(
      <MarketPluginTile
        plugin={{ id: "notes", installed: true, update_available: true }}
        installing={false}
        onInstall={onInstall}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "plugins.marketUpdate" }),
    );
    expect(onInstall).toHaveBeenLastCalledWith(true);
    rerender(
      <MarketPluginTile
        plugin={{ id: "notes", installed: true, update_available: false }}
        installing={false}
        onInstall={onInstall}
      />,
    );
    expect(
      screen.getByRole("button", { name: "plugins.marketInstalled" }),
    ).toBeDisabled();
    expect(onInstall).toHaveBeenCalledTimes(2);
  });
  it("requires confirmation before uninstalling and prevents opening details", async () => {
    const onOpen = vi.fn(),
      onUninstall = vi.fn();
    render(
      <InstalledPluginTile
        plugin={{ id: "notes", name: "Notes" }}
        toggling={false}
        onOpen={onOpen}
        onToggle={vi.fn()}
        onUninstall={onUninstall}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "plugins.uninstall" }),
    );
    expect(onUninstall).not.toHaveBeenCalled();
    expect(onOpen).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("button", { name: "OK" }));
    expect(onUninstall).toHaveBeenCalledOnce();
    expect(onOpen).not.toHaveBeenCalled();
  });
});
