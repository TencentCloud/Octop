import { App } from "antd";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  mobile: false,
  createBackup: vi.fn(),
  restoreBackup: vi.fn(),
  syncFromServer: vi.fn(),
  setOnSettled: vi.fn(),
  t: (key: string) => key,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: state.t }),
}));
vi.mock("../../../hooks/useIsMobile", () => ({
  useIsMobile: () => state.mobile,
}));
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));
vi.mock("../../../context/ServiceRestartContext", () => ({
  useServiceRestartContext: () => ({ isRestarting: false }),
}));
vi.mock("../../../context/BackupOperationContext", () => ({
  useBackupOperation: () => ({
    kind: null,
    restoreTarget: null,
    uploadPercent: null,
    busy: false,
    creating: false,
    restoring: false,
    autoRunning: false,
    createBackup: state.createBackup,
    restoreBackup: state.restoreBackup,
    syncFromServer: state.syncFromServer,
    setOnSettled: state.setOnSettled,
  }),
}));
vi.mock("../../../api/modules/backup", () => ({
  backupApi: { listBackups: vi.fn(), getAutoSettings: vi.fn() },
}));

import { backupApi } from "../../../api/modules/backup";
import BackupRestorePanel from "./index";

const note = "升级前的稳定版本 <script>alert(1)</script>";
const item = {
  name: "octop-backup-20261022T000000Z.tar.gz",
  size: 1024,
  created_at: "2026-10-22T00:00:00Z",
  modified_at: "2026-10-22T00:00:00Z",
  note,
};

async function openPanel() {
  const result = render(
    <App>
      <BackupRestorePanel />
    </App>,
  );
  await screen.findByText(item.name);
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  state.mobile = false;
  state.createBackup.mockResolvedValue(true);
  state.restoreBackup.mockResolvedValue(true);
  vi.mocked(backupApi.listBackups).mockResolvedValue({
    dir: "backups",
    items: [item],
  });
  vi.mocked(backupApi.getAutoSettings).mockResolvedValue({
    auto_enabled: false,
    schedule: "cron:0 4 * * *",
    retention_count: 7,
    include_config: true,
    include_workspaces: true,
    include_skill_packages: true,
    include_plugins: true,
    include_knowledge: true,
    include_chats: false,
  });
});

describe("system backup notes", () => {
  it.each([false, true])(
    "shows notes as plain text (mobile=%s)",
    async (mobile) => {
      state.mobile = mobile;
      const { container } = await openPanel();
      expect(screen.getByText(note)).toBeVisible();
      expect(container.querySelector("script")).toBeNull();
    },
  );

  it("passes the optional note with the selected contents and clears it after success", async () => {
    await openPanel();
    fireEvent.click(
      screen.getByRole("button", { name: "backup.createButton" }),
    );
    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByRole("textbox", {
      name: "backup.noteLabel",
    });
    expect(input).toHaveAttribute("maxlength", "500");
    fireEvent.change(input, { target: { value: "Before upgrading" } });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "backup.createButton" }),
    );
    await waitFor(() =>
      expect(state.createBackup).toHaveBeenCalledWith({
        note: "Before upgrading",
        include_config: true,
        include_workspaces: true,
        include_skill_packages: true,
        include_plugins: true,
        include_knowledge: true,
        include_chats: false,
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "backup.createButton" }),
    );
    expect(
      screen.getByRole("textbox", { name: "backup.noteLabel" }),
    ).toHaveValue("");
  });

  it("keeps the note and dialog available when creation fails", async () => {
    state.createBackup.mockResolvedValue(false);
    await openPanel();
    fireEvent.click(
      screen.getByRole("button", { name: "backup.createButton" }),
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox"), {
      target: { value: "Retry me" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "backup.createButton" }),
    );
    await waitFor(() => expect(state.createBackup).toHaveBeenCalled());
    expect(within(dialog).getByRole("textbox")).toHaveValue("Retry me");
    await waitFor(() => expect(dialog).toBeVisible());
  });

  it("cancels without creating a backup and starts with an empty note next time", async () => {
    await openPanel();
    fireEvent.click(
      screen.getByRole("button", { name: "backup.createButton" }),
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox"), {
      target: { value: "Discard me" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.cancel" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(state.createBackup).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "backup.createButton" }),
    );
    expect(
      screen.getByRole("textbox", { name: "backup.noteLabel" }),
    ).toHaveValue("");
  });

  it("shows the selected note in the restore confirmation", async () => {
    await openPanel();
    fireEvent.click(
      screen.getByRole("button", { name: "backup.restoreAction" }),
    );
    await waitFor(() =>
      expect(within(screen.getByRole("dialog")).getByText(note)).toBeVisible(),
    );
    expect(state.restoreBackup).not.toHaveBeenCalled();
  });

  it("shows legacy backups that have no note", async () => {
    const { note: _note, ...legacy } = item;
    vi.mocked(backupApi.listBackups).mockResolvedValue({
      dir: "backups",
      items: [legacy],
    });
    await openPanel();
    expect(screen.queryByText(note)).not.toBeInTheDocument();
  });
});
