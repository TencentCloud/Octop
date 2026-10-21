import { request } from "../request";

export type TextAssistKind =
  | "chat.prompt"
  | "expert.description"
  | "expert.welcome_message"
  | "team.description"
  | "team.welcome_message"
  | "skill_package.description"
  | "knowledge_base.description";

export type TextAssistRequest = {
  kind: TextAssistKind;
  text?: string;
  context?: { name?: string; [key: string]: unknown };
  locale?: string | null;
  default_model?: string | null;
  agent_id?: string | null;
};

export const textAssistApi = {
  assist: (body: TextAssistRequest) =>
    request<{ text: string }>("/text/assist", {
      method: "POST",
      body: JSON.stringify({
        kind: body.kind,
        text: body.text ?? "",
        context: body.context ?? {},
        ...(body.locale ? { locale: body.locale } : {}),
        ...(body.default_model ? { default_model: body.default_model } : {}),
        ...(body.agent_id ? { agent_id: body.agent_id } : {}),
      }),
    }),
};
