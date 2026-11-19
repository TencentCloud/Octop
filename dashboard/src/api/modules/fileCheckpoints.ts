import { request } from "../request";

export interface TurnSummaryFile {
  path: string;
  added: number;
  removed: number;
  write_count: number;
  tool_names: string[];
}

export interface TurnSummary {
  files: TurnSummaryFile[];
  additions: number;
  deletions: number;
  reverted: boolean;
}

export interface RewindFile {
  path: string;
  before: string | null;
  after: string | null;
  reason?: string | null;
  write_count?: number | null;
  tool_names?: string[] | null;
}

export interface RewindPreview {
  safe: RewindFile[];
  unsafe: RewindFile[];
  ignored: RewindFile[];
  can_apply: boolean;
}

const base = (agentId: string, threadId: string, messageId: string) =>
  `/agents/${agentId}/threads/${threadId}/messages/${messageId}/files`;

export const fileCheckpointsApi = {
  turnSummary: (
    agentId: string,
    threadId: string,
    messageId: string,
  ): Promise<TurnSummary> =>
    request(`${base(agentId, threadId, messageId)}/summary`),

  turnDiff: (
    agentId: string,
    threadId: string,
    messageId: string,
    path: string,
  ): Promise<{ path: string; diff: string }> =>
    request(
      `${base(agentId, threadId, messageId)}/diff?path=${encodeURIComponent(
        path,
      )}`,
    ),

  rewindPreview: (
    agentId: string,
    threadId: string,
    messageId: string,
  ): Promise<RewindPreview> =>
    request(`${base(agentId, threadId, messageId)}/rewind/preview`),

  rewindApply: (
    agentId: string,
    threadId: string,
    messageId: string,
  ): Promise<{ applied: string[]; blocked: string[] }> =>
    request(`${base(agentId, threadId, messageId)}/rewind/apply`, {
      method: "POST",
    }),
};
