import { request } from "../request";

export interface RewindFile {
  path: string;
  before: string | null;
  after: string | null;
  reason?: string | null;
}

export interface RewindPreview {
  safe: RewindFile[];
  unsafe: RewindFile[];
  ignored: RewindFile[];
}

const base = (agentId: string, threadId: string, messageId: string) =>
  `/agents/${agentId}/threads/${threadId}/messages/${messageId}/files`;

export const fileCheckpointsApi = {
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
  ): Promise<{ applied: string[] }> =>
    request(`${base(agentId, threadId, messageId)}/rewind/apply`, {
      method: "POST",
    }),
};
