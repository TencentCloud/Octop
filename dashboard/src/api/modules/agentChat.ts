import { request } from "../request";
import type { LocalizedText } from "../../utils/localizedText";
import type { SecureFormPendingRecord } from "../types/hitl";

export interface ChatWelcomeResponse {
  welcome_message?: LocalizedText;
  quick_prompts?: Array<{
    title: LocalizedText;
    description: LocalizedText;
    prompt: LocalizedText;
    color?: string;
    icon_name?: string | null;
    expert?: string;
    agent_id?: string;
  }>;
  task_examples?: { zh?: string[]; en?: string[] } | null;
}

export const agentChatApi = {
  welcome: (agentId: string) =>
    request<ChatWelcomeResponse>(
      `/agents/${encodeURIComponent(agentId)}/chat/welcome`,
    ),
  /**
   * Server-registered schema for one pending secure form. The modal renders
   * fields and destination facts ONLY from this record; 410 once expired.
   */
  secureForm: (agentId: string, pendingId: string) =>
    request<SecureFormPendingRecord>(
      `/agents/${encodeURIComponent(
        agentId,
      )}/chat/secure-form/${encodeURIComponent(pendingId)}`,
    ),
};
