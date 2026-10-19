import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import SqliteBackups from "./SqliteBackups";
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "Asia/Shanghai",
}));
vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: { storageBackups: vi.fn(), deleteStorageBackup: vi.fn() },
}));
const api = vi.mocked(memoryDashboardApi);
const backup = {
  backup_id: "memory.sqlite.before-slim.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.bak",
  created_at: 10,
  size_bytes: 4096,
  kind: "before_maintenance" as const,
};
beforeEach(() => {
  vi.clearAllMocks();
  api.storageBackups.mockResolvedValue([backup]);
  api.deleteStorageBackup.mockResolvedValue(undefined);
});
describe("SQLite restore confirmation", () => {
  it("lists only the requested expert and restores the selected identifier after confirmation", async () => {
    const user = userEvent.setup();
    const restore = vi.fn().mockResolvedValue(undefined);
    render(
      <SqliteBackups
        agentId="expert-a"
        refreshKey={1}
        disabled={false}
        onRestore={restore}
      />,
    );
    await screen.findByText(backup.backup_id);
    expect(api.storageBackups).toHaveBeenCalledWith("expert-a");
    await user.click(
      screen.getByRole("button", { name: "memory.storage.restoreThis" }),
    );
    expect(restore).not.toHaveBeenCalled();
    expect(
      screen.getByText("memory.storage.restoreWarning"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(restore).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "memory.storage.restoreThis" }),
    );
    await user.click(
      screen.getByRole("button", { name: "memory.storage.restoreConfirm" }),
    );
    await waitFor(() =>
      expect(restore).toHaveBeenCalledExactlyOnceWith(backup.backup_id),
    );
  });
  it("blocks restore while the current expert cannot be maintained", async () => {
    render(
      <SqliteBackups
        agentId="expert-a"
        refreshKey={1}
        disabled
        onRestore={vi.fn()}
      />,
    );
    expect(
      await screen.findByRole("button", { name: "memory.storage.restoreThis" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "memory.storage.deleteBackup" }),
    ).toBeDisabled();
  });
  it("keeps failed restore visible without claiming success", async () => {
    const user = userEvent.setup();
    const restore = vi
      .fn()
      .mockRejectedValue(new Error("backup validation failed"));
    render(
      <SqliteBackups
        agentId="expert-a"
        refreshKey={1}
        disabled={false}
        onRestore={restore}
      />,
    );
    await user.click(
      await screen.findByRole("button", { name: "memory.storage.restoreThis" }),
    );
    await user.click(
      screen.getByRole("button", { name: "memory.storage.restoreConfirm" }),
    );
    await screen.findAllByText("backup validation failed");
    expect(
      screen.getByRole("button", { name: "memory.storage.restoreConfirm" }),
    ).toBeEnabled();
  });
});

describe("SQLite backup deletion", () => {
  it("requires confirmation and removes only the selected row after success", async () => {
    const user = userEvent.setup();
    const restore = vi.fn();
    render(
      <SqliteBackups
        agentId="expert-a"
        refreshKey={1}
        disabled={false}
        onRestore={restore}
      />,
    );
    await user.click(
      await screen.findByRole("button", {
        name: "memory.storage.deleteBackup",
      }),
    );
    expect(
      screen.getByText("memory.storage.deleteBackupWarning"),
    ).toBeInTheDocument();
    expect(api.deleteStorageBackup).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(api.deleteStorageBackup).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "memory.storage.deleteBackup" }),
    );
    await user.click(
      screen.getByRole("button", {
        name: "memory.storage.deleteBackupConfirm",
      }),
    );
    await waitFor(() =>
      expect(api.deleteStorageBackup).toHaveBeenCalledExactlyOnceWith(
        "expert-a",
        backup.backup_id,
      ),
    );
    await screen.findByText("memory.storage.noBackups");
    expect(restore).not.toHaveBeenCalled();
  });
  it("retains the backup and shows failure when deletion fails", async () => {
    api.deleteStorageBackup.mockRejectedValue(new Error("permission denied"));
    const user = userEvent.setup();
    render(
      <SqliteBackups
        agentId="expert-a"
        refreshKey={1}
        disabled={false}
        onRestore={vi.fn()}
      />,
    );
    await user.click(
      await screen.findByRole("button", {
        name: "memory.storage.deleteBackup",
      }),
    );
    await user.click(
      screen.getByRole("button", {
        name: "memory.storage.deleteBackupConfirm",
      }),
    );
    await screen.findAllByText("permission denied");
    expect(
      screen.getByRole("button", {
        name: "memory.storage.deleteBackupConfirm",
      }),
    ).toBeEnabled();
    expect(screen.getAllByText(backup.backup_id).length).toBeGreaterThan(0);
  });
});
