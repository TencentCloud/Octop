import { request } from "../request";
import type {
  MBTIType,
  MBTITestQuestion,
  MBTITestResult,
  MBTIApplyResponse,
} from "../types";

function agentHeaders(agentId?: string): HeadersInit | undefined {
  if (!agentId) return undefined;
  return { "X-Agentbuddy-Agent-Id": agentId };
}

export const mbtiApi = {
  /** Get currently configured MBTI type from the active agent. */
  getCurrentMBTI: (agentId?: string) =>
    request<{ code: string; configured: boolean }>("/mbti/current", {
      headers: agentHeaders(agentId),
    }),

  /** List all 16 MBTI types. */
  listMBTITypes: () => request<MBTIType[]>("/mbti/types"),

  /** Get details for a single MBTI type. */
  getMBTIType: (code: string) => request<MBTIType>(`/mbti/types/${code}`),

  /** Get all 28 test questions. */
  getMBTITestQuestions: () =>
    request<MBTITestQuestion[]>("/mbti/test/questions"),

  /** Submit test answers and get result. */
  submitMBTITest: (
    answers: Record<string, string>,
    autoApply = false,
    language = "zh",
    agentId?: string,
  ) =>
    request<MBTITestResult>("/mbti/test/submit", {
      method: "POST",
      body: JSON.stringify({
        answers,
        auto_apply: autoApply,
        language,
      }),
      headers: agentHeaders(agentId),
    }),

  /** Apply a specific MBTI type to the active agent (regenerates SOUL.md). */
  applyMBTIType: (code: string, language = "zh", agentId?: string) =>
    request<MBTIApplyResponse>("/mbti/apply", {
      method: "POST",
      body: JSON.stringify({ code, language }),
      headers: agentHeaders(agentId),
    }),
};
