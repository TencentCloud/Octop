/**
 * memoryPortable — memory migration API module
 *
 * Backend routes:
 *   GET  /api/memory/portable/sources
 *   POST /api/agents/{aid}/memory/portable/pack      -> blob download
 *   POST /api/agents/{aid}/memory/portable/adopt     -> multipart upload
 *   POST /api/agents/{aid}/memory/portable/doctor    -> multipart upload, optional pkg
 */

import { requestBlob, requestUpload } from "../request";
import { saveBlobAsFile } from "../../utils/saveBlobAsFile";

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

export interface PortableSource {
  host_kind: string;
  db_path: string;
  namespace: string;
  agent_name?: string;
  raw_event_count: number;
  atom_count: number;
  entity_count: number;
  journal_count: number;
  schema_version?: string;
}

export interface AdoptSummary {
  target_namespace: string;
  target_db_path: string;
  applied: number;
  skipped: number;
  errors: number;
  dry_run: boolean;
  already_adopted: boolean;
  already_adopted_at?: string;
  applied_by_table?: Record<string, number>;
  skipped_by_table?: Record<string, number>;
}

export interface DoctorCheck {
  name: string;
  passed: boolean;
  message?: string;
  hint?: string;
}

export interface DoctorReport {
  host: string;
  namespace?: string;
  db_path?: string;
  checks: DoctorCheck[];
  all_passed: boolean;
  compared_with?: string;
  row_count_diff?: Record<string, number>;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** List all migratable memory stores on this machine. */
async function listSources(): Promise<PortableSource[]> {
  const { request } = await import("../request");
  const res = await request<{ sources: PortableSource[] }>(
    "/memory/portable/sources",
  );
  return res.sources;
}

/** Pack an agent's memory as .hmpkg and trigger a browser download. */
async function packAndDownload(agentId: string): Promise<void> {
  const blob = await requestBlob(`/agents/${agentId}/memory/portable/pack`, {
    method: "POST",
  });
  const now = new Date();
  const ts = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(
    2,
    "0",
  )}${String(now.getDate()).padStart(2, "0")}-${String(now.getHours()).padStart(
    2,
    "0",
  )}${String(now.getMinutes()).padStart(2, "0")}`;
  const filename = `${agentId}-${ts}.hmpkg`;
  await saveBlobAsFile(blob, filename);
}

/** Upload an .hmpkg file and import it into the target host. */
async function adoptMemory(
  agentId: string,
  file: File,
  opts: {
    targetHost: string;
    targetNamespace?: string;
    onConflict?: "skip" | "replace" | "raise";
    hostRewrite?: "keep" | "target";
    dryRun?: boolean;
  },
): Promise<AdoptSummary> {
  const form = new FormData();
  form.append("pkg_file", file);
  form.append("target_host", opts.targetHost);
  if (opts.targetNamespace)
    form.append("target_namespace", opts.targetNamespace);
  form.append("on_conflict", opts.onConflict ?? "skip");
  form.append("host_rewrite", opts.hostRewrite ?? "keep");
  form.append("dry_run", String(opts.dryRun ?? false));

  return requestUpload<AdoptSummary>(
    `/agents/${agentId}/memory/portable/adopt`,
    form,
  );
}

/** Run health checks against the target db. */
async function doctorMemory(
  agentId: string,
  opts: {
    hostSpec?: string;
    comparePkg?: File;
  } = {},
): Promise<DoctorReport> {
  const form = new FormData();
  form.append("host_spec", opts.hostSpec ?? "agent");
  if (opts.comparePkg) form.append("compare_pkg", opts.comparePkg);

  return requestUpload<DoctorReport>(
    `/agents/${agentId}/memory/portable/doctor`,
    form,
  );
}

const memoryPortableApi = {
  listSources,
  packAndDownload,
  adoptMemory,
  doctorMemory,
};

export default memoryPortableApi;
