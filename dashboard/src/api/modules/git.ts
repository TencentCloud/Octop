import { request } from "../request";

export type GitChangeStatus =
  | "modified"
  | "added"
  | "deleted"
  | "renamed"
  | "copied"
  | "typechange"
  | "untracked"
  | "conflicted";

export interface GitFileChange {
  path: string;
  status: GitChangeStatus;
  staged: boolean;
  added: number | null;
  removed: number | null;
  orig_path?: string | null;
}

export interface GitStatus {
  is_repo: boolean;
  git_available: boolean;
  branch: string | null;
  upstream: string | null;
  ahead: number;
  behind: number;
  head_short: string | null;
  files: GitFileChange[];
  added: number;
  removed: number;
}

export interface GitDiff {
  path: string;
  diff: string;
  truncated: boolean;
}

export interface GitCommitEntry {
  sha: string;
  short: string;
  author: string;
  date: string;
  subject: string;
}

export const gitApi = {
  status: (agentId: string): Promise<GitStatus> =>
    request<GitStatus>(`/agents/${agentId}/git/status`),

  diff: (agentId: string, path: string, staged: boolean): Promise<GitDiff> =>
    request<GitDiff>(
      `/agents/${agentId}/git/diff?path=${encodeURIComponent(path)}&staged=${
        staged ? "true" : "false"
      }`,
    ),

  log: (agentId: string, limit = 30): Promise<GitCommitEntry[]> =>
    request<GitCommitEntry[]>(`/agents/${agentId}/git/log?limit=${limit}`),

  stage: (agentId: string, paths: string[]): Promise<{ ok: boolean }> =>
    request<{ ok: boolean }>(`/agents/${agentId}/git/stage`, {
      method: "POST",
      body: JSON.stringify({ paths }),
    }),

  unstage: (agentId: string, paths: string[]): Promise<{ ok: boolean }> =>
    request<{ ok: boolean }>(`/agents/${agentId}/git/unstage`, {
      method: "POST",
      body: JSON.stringify({ paths }),
    }),

  discard: (agentId: string, paths: string[]): Promise<{ ok: boolean }> =>
    request<{ ok: boolean }>(`/agents/${agentId}/git/discard`, {
      method: "POST",
      body: JSON.stringify({ paths }),
    }),

  commit: (agentId: string, message: string): Promise<{ commit: string }> =>
    request<{ commit: string }>(`/agents/${agentId}/git/commit`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
