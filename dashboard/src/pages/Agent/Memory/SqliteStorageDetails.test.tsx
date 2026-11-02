import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MemoryStorageInspection } from "../../../api/modules/memoryDashboard";
import SqliteStorageDetails from "./SqliteStorageDetails";

const snapshot = {
  backend: "sqlite",
  elapsed_ms: 12.34,
  file_check_ms: 0.25,
  file_size: 8192,
  wal_size: 0,
  reclaimable_bytes: 0,
  checkpoints_available: true,
  memory_counts: [
    { table: "raw_events", rows: 0, status: "ok", elapsed_ms: 0.12 },
    { table: "atoms", rows: null, status: "missing", elapsed_ms: 0 },
    { table: "journal", rows: null, status: "timed_out", elapsed_ms: 5 },
  ],
  checkpoint_counts: [
    { table: "checkpoints", rows: 123, status: "ok", elapsed_ms: 0.5 },
  ],
} as MemoryStorageInspection;

describe("SQLite storage details", () => {
  it("shows measured timings and distinguishes zero, missing tables and timeouts", () => {
    render(<SqliteStorageDetails inspection={snapshot} />);
    expect(screen.getByText("12.34 ms")).toBeInTheDocument();
    expect(screen.getByText("0.25 ms")).toBeInTheDocument();
    expect(screen.getByText("123")).toBeInTheDocument();
    expect(
      screen.getByText("memory.storage.count_missing"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("memory.storage.count_timed_out"),
    ).toBeInTheDocument();
    const row = screen
      .getByText("memory.storage.tables.raw_events")
      .closest("tr")!;
    expect(within(row).getByText("0")).toBeInTheDocument();
  });
  it("does not expose checkpoint counts for a shared store", () => {
    render(
      <SqliteStorageDetails
        inspection={{ ...snapshot, checkpoints_available: false }}
      />,
    );
    expect(
      screen.getByText("memory.storage.sharedCheckpointHint"),
    ).toBeInTheDocument();
    expect(screen.queryByText("123")).not.toBeInTheDocument();
  });
  it("compares saved snapshots and never treats a missing measurement as zero", () => {
    const before = {
      ...snapshot,
      checkpoint_counts: [
        {
          table: "checkpoints",
          rows: 120,
          status: "ok" as const,
          elapsed_ms: 1,
        },
      ],
    };
    render(<SqliteStorageDetails inspection={snapshot} before={before} />);
    const row = screen
      .getByText("memory.storage.tables.checkpoints")
      .closest("tr")!;
    for (const value of ["120", "123", "+3"])
      expect(within(row).getByText(value)).toBeInTheDocument();
    const missing = screen
      .getByText("memory.storage.tables.atoms")
      .closest("tr")!;
    expect(within(missing).getByText("—")).toBeInTheDocument();
    expect(
      screen.getByText("memory.storage.comparisonHint"),
    ).toBeInTheDocument();
  });
});
