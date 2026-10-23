import { request } from "../request";

export interface SandboxAgentRef {
  agent_id: string;
  name: string | null;
}

export interface SandboxEntry {
  container_name: string;
  container_id: string;
  scope: string;
  agent_id: string | null;
  status: string;
  created_at: string;
  image: string;
  network_offline: boolean | null;
  expected_image: string | null;
  expected_allow_network: boolean | null;
  drift: boolean | null;
  network_drift: boolean | null;
  affected_agents: SandboxAgentRef[];
}

export interface SandboxRecreateResult {
  recreated: boolean;
  container_name: string;
  backup_path: string;
  old_image: string | null;
  expected_image: string | null;
  old_network_offline: boolean | null;
  expected_allow_network: boolean | null;
}

export interface SandboxImageRow {
  tag: string | null;
  id: string;
  size: number;
  created: string | number | null;
  referenced: boolean;
}

export const sandboxAdminApi = {
  list: () => request<SandboxEntry[]>("/admin/sandboxes"),
  recreate: (containerName: string) =>
    request<SandboxRecreateResult>(
      `/admin/sandboxes/${encodeURIComponent(containerName)}/recreate`,
      { method: "POST" },
    ),
  images: () => request<SandboxImageRow[]>("/admin/sandboxes/images"),
  backups: (containerName: string) =>
    request<{ stamp: string; path: string; meta: Record<string, unknown> }[]>(
      `/admin/sandboxes/backups/${encodeURIComponent(containerName)}`,
    ),
};
