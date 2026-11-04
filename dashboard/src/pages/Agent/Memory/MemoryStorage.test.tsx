import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  memoryDashboardApi,
  type MemoryStorageInspection,
  type MemoryStorageJob,
} from "../../../api/modules/memoryDashboard";
import MemoryStorage from "./MemoryStorage";
import { message } from "../../../utils/antdMessage";

vi.mock("../../../utils/antdMessage", () => ({
  message: { success: vi.fn() },
}));
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "Asia/Shanghai",
}));

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    checkStorage: vi.fn(),
    storageMaintenanceStatus: vi.fn(),
    startStorageMaintenance: vi.fn(),
    storageBackups: vi.fn(),
    restoreStorage: vi.fn(),
  },
}));
const api = vi.mocked(memoryDashboardApi);
const inspection: MemoryStorageInspection = {
  backend: "sqlite",
  scope: "agent",
  maintenance_supported: true,
  blocked_reason: null,
  checked_at: 1,
  file_size: 8192,
  wal_size: 0,
  reclaimable_bytes: 4096,
  auto_vacuum_enabled: true,
  tables: [],
};
const job: MemoryStorageJob = {
  job_id: "j1",
  scope: "agent",
  phase: "deduplicating",
  started_at: 1,
  updated_at: 2,
  scanned: 2,
  total: 10,
};
const pgInspection: MemoryStorageInspection = {
  backend: "postgres",
  scope: "agent",
  maintenance_supported: true,
  checked_at: 1,
  namespace: "agent_a",
  tables: [],
  namespace_tables: [{ table: "candidates", rows: 37, row_bytes: 1024 }],
  cleanup_preview: {
    candidates: 2,
    journal: 8,
    total: 10,
    limit_per_table: 500,
    candidate_days: 30,
    journal_days: 14,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.checkStorage.mockResolvedValue(inspection);
  api.storageBackups.mockResolvedValue([]);
  api.storageMaintenanceStatus.mockResolvedValue({ busy: false, job: null });
  api.startStorageMaintenance.mockResolvedValue({ busy: true, job });
});

describe("memory storage", () => {
  it("gives loading and completion feedback when manual inspection returns unchanged data", async () => {
    const user = userEvent.setup();
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("8.0 KB");
    expect(message.success).not.toHaveBeenCalled();
    let resolveCheck!: (value: MemoryStorageInspection) => void;
    api.checkStorage.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveCheck = resolve;
        }),
    );
    await user.click(
      screen.getByRole("button", { name: "memory.storage.check" }),
    );
    expect(
      screen.getByRole("button", { name: "loading memory.storage.checking" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    ).toBeDisabled();
    await act(async () => resolveCheck({ ...inspection, checked_at: 2 }));
    expect(message.success).toHaveBeenCalledWith(
      "memory.storage.checkComplete",
    );
    expect(screen.getByText("memory.storage.lastChecked")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "memory.storage.check" }),
    ).toBeEnabled();
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
  });
  it("allows read-only inspection after initial maintenance status failure but keeps writes disabled", async () => {
    const user = userEvent.setup();
    api.storageMaintenanceStatus.mockRejectedValue(
      new Error("status unavailable"),
    );
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("memory.storage.connectionLost");
    await user.click(
      screen.getByRole("button", { name: "memory.storage.check" }),
    );
    await screen.findByText("8.0 KB");
    expect(api.checkStorage).toHaveBeenCalledWith("a");
    expect(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    ).toBeDisabled();
  });
  it("inspects without mutation and starts only after confirmation", async () => {
    const user = userEvent.setup();
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("8.0 KB");
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    );
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "memory.storage.confirmStart" }),
    );
    await waitFor(() =>
      expect(api.startStorageMaintenance).toHaveBeenCalledWith("a"),
    );
    await screen.findByText("deduplicating");
    expect(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    ).toBeDisabled();
  });
  it("previews only PostgreSQL expert data and requires cleanup confirmation", async () => {
    const user = userEvent.setup();
    api.checkStorage.mockResolvedValue(pgInspection);
    api.startStorageMaintenance.mockResolvedValue({
      busy: true,
      job: { ...job, backend: "postgres", phase: "cleaning" },
    });
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("37");
    expect(
      screen.getByText("memory.storage.scope_namespace"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("memory.storage.cleanupPreview"),
    ).toBeInTheDocument();
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    );
    expect(
      screen.getByText("memory.storage.pgConfirmBody", { exact: false }),
    ).toBeInTheDocument();
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "memory.storage.confirmStart" }),
    );
    await screen.findByText("cleaning");
    expect(api.startStorageMaintenance).toHaveBeenCalledWith("a");
  });
  it("disables maintenance for colliding PostgreSQL namespaces", async () => {
    api.checkStorage.mockResolvedValue({
      ...pgInspection,
      maintenance_supported: false,
      blocked_reason: "shared_namespace",
    });
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("memory.storage.blocked_shared_namespace");
    expect(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    ).toBeDisabled();
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
  });
  it.each([0, 10])(
    "reports PostgreSQL cleanup of %i rows without promising disk reduction",
    async (total) => {
      api.checkStorage.mockResolvedValue(pgInspection);
      api.storageMaintenanceStatus.mockResolvedValue({
        busy: false,
        job: {
          ...job,
          backend: "postgres",
          phase: "done",
          report: {
            backend: "postgres",
            operation: "namespace_cleanup",
            namespace: "agent_a",
            candidates_deleted: total ? 2 : 0,
            journal_deleted: total ? 8 : 0,
            total_deleted: total,
            limit_per_table: 500,
            backup_path: total ? "server/backup.jsonl" : null,
            backup_bytes: total ? 1024 : 0,
            physical_space_reclaimed: false,
          },
        },
      });
      render(<MemoryStorage agentId="a" />);
      await screen.findByText("memory.storage.cleanedRows");
      expect(
        screen.queryByText("memory.storage.reduced"),
      ).not.toBeInTheDocument();
      if (total) {
        expect(screen.getByText("server/backup.jsonl")).toBeInTheDocument();
      } else {
        expect(screen.getByText("memory.storage.pgNoop")).toBeInTheDocument();
        expect(
          screen.queryByText("memory.storage.backup"),
        ).not.toBeInTheDocument();
      }
    },
  );
  it("restores an active job when the page opens without starting another", async () => {
    api.storageMaintenanceStatus.mockResolvedValue({ busy: true, job });
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("deduplicating");
    expect(api.checkStorage).not.toHaveBeenCalled();
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
  });
  it("displays the completed result and backup separately", async () => {
    api.storageMaintenanceStatus.mockResolvedValue({
      busy: false,
      job: {
        ...job,
        phase: "done",
        report: {
          before: { file_bytes: 8192, wal_bytes: 0 },
          after: { file_bytes: 4096, wal_bytes: 0 },
          backup_path: "server/memory.bak",
          backup_bytes: 8192,
          stats: { scanned: 10, rewritten: 3 },
        },
      },
    });
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("server/memory.bak");
    expect(screen.getByText("memory.storage.reduced")).toBeInTheDocument();
    expect(
      screen.getAllByText("memory.storage.backupSize").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("10")).toBeInTheDocument();
    await waitFor(() => expect(api.checkStorage).toHaveBeenCalledTimes(1));
  });
  it("shows failure details and supports retry after inspection", async () => {
    api.storageMaintenanceStatus.mockResolvedValue({
      busy: false,
      job: { ...job, phase: "failed", error: "disk full" },
    });
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("disk full");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "memory.storage.maintain" }),
      ).toBeEnabled(),
    );
  });
  it("retains the page and explains an inspection failure", async () => {
    api.checkStorage.mockRejectedValue(new Error("expert stopped"));
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("expert stopped");
    expect(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    ).toBeDisabled();
  });
  it("does not start if confirmation is cancelled", async () => {
    const user = userEvent.setup();
    render(<MemoryStorage agentId="a" />);
    await screen.findByText("8.0 KB");
    await user.click(
      screen.getByRole("button", { name: "memory.storage.maintain" }),
    );
    await user.click(screen.getByRole("button", { name: "common.cancel" }));
    expect(api.startStorageMaintenance).not.toHaveBeenCalled();
  });
});
