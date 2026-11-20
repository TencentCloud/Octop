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

export interface GitHistoryRow {
  graph: string;
  sha?: string | null;
  short?: string | null;
  author?: string | null;
  committer?: string | null;
  date?: string | null;
  refs?: string | null;
  signature?: string | null;
  signer?: string | null;
  subject?: string | null;
}

export interface GitPushResult {
  branch: string;
  remote: string;
  upstream: string;
  set_upstream: boolean;
  output: string;
}

export interface GitCommitResult {
  commit: string;
  message: string;
  pushed: boolean;
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

  commitAdvanced: (
    agentId: string,
    body: { message: string; include_unstaged: boolean; push: boolean },
  ): Promise<GitCommitResult> =>
    request<GitCommitResult>(`/agents/${agentId}/git/commit`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  generateMessage: (
    agentId: string,
    includeUnstaged: boolean,
  ): Promise<{ message: string }> =>
    request<{ message: string }>(`/agents/${agentId}/git/message`, {
      method: "POST",
      body: JSON.stringify({ include_unstaged: includeUnstaged }),
    }),

  push: (agentId: string): Promise<GitPushResult> =>
    request<GitPushResult>(`/agents/${agentId}/git/push`, { method: "POST" }),

  history: (agentId: string, limit = 50): Promise<GitHistoryRow[]> =>
    request<GitHistoryRow[]>(`/agents/${agentId}/git/history?limit=${limit}`),
};
