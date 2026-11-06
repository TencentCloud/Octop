export type HitlSessionMode = "ask" | "allow_all" | "allow_tools";

export interface HitlSessionPolicy {
  mode: HitlSessionMode;
  tools?: string[];
}

export type HitlDecision = { type: string; message?: string };

export type HitlDecisionHandler = (
  decisions: HitlDecision[],
  policy?: HitlSessionPolicy,
  pendingId?: string,
) => void;

export interface HitlActionRequest {
  name: string;
  args?: Record<string, unknown>;
  description?: string;
}

export interface HitlReviewConfig {
  action_name: string;
  allowed_decisions: string[];
}

export interface HitlPendingPayload {
  pending_id?: string;
  action_requests: HitlActionRequest[];
  review_configs?: HitlReviewConfig[];
}

/** Tool whose HITL pause is a question for the user, not an approval. */
export const ASK_USER_TOOL_NAME = "ask_user_question";

/** Tool whose HITL pause collects a secret through the masked input card. */
export const REQUEST_SECRET_INPUT_TOOL_NAME = "request_secret_input";

/** Tool whose HITL pause collects a multi-field secure form. */
export const REQUEST_SECURE_FORM_TOOL_NAME = "request_secure_form";

export interface SecretInputRequest {
  slot: string;
  prompt: string;
  title?: string;
}

export type SecureFormFieldType =
  | "text"
  | "password"
  | "otp"
  | "card_number"
  | "card_exp"
  | "card_cvv";

export type SecureFormVaultItemType = "login" | "card" | "contact";

export interface SecureFormVaultMeta {
  item_type: SecureFormVaultItemType;
  title: string;
  origin?: string | null;
}

export interface SecureFormRouting {
  kind: "env" | "vault";
  /** env routing: field id -> normalized slot name (server fact). */
  slots?: Record<string, string> | null;
  vault_meta?: SecureFormVaultMeta | null;
}

export interface SecureFormField {
  id: string;
  label: string;
  type: SecureFormFieldType;
  required: boolean;
  max_length?: number | null;
}

/**
 * Server-registered secure-form schema from
 * ``GET /api/agents/{id}/chat/secure-form/{pending_id}``.
 *
 * The ONLY source the modal may render fields and destination facts from —
 * never SSE ``tool_start`` args. Collision/slot facts are re-derived per
 * call. Values are never included.
 */
export interface SecureFormPendingRecord {
  pending_id: string;
  thread_id: string;
  agent_id: string;
  title?: string | null;
  prompt: string;
  status: string;
  fields: SecureFormField[];
  routing: SecureFormRouting;
  existing_vault_item_id?: string | null;
  existing_slot_names?: string[];
  vault_storable_field_ids?: string[];
}

/** Launcher display data from the pause args (title/prompt only, non-sensitive). */
export interface SecureFormLauncherRequest {
  title?: string;
  prompt: string;
  fieldCount: number;
}

export interface AskOption {
  label: string;
  description?: string;
}

export interface AskQuestion {
  question: string;
  header?: string;
  options?: AskOption[];
  multi_select?: boolean;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function parseJsonObject(raw: unknown): unknown {
  if (typeof raw !== "string") return raw;
  const text = raw.trim();
  if (!text) return raw;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return raw;
  }
}

/** Parse HITL ``args`` whether the provider sent an object or a JSON string. */
export function parseActionArgs(raw: unknown): Record<string, unknown> {
  return asRecord(parseJsonObject(raw)) ?? {};
}

/** Unwrap LangGraph Interrupt envelopes so `action_requests` is top-level. */
export function normalizeHitlRequest(raw: unknown): Record<string, unknown> {
  const fallback = asRecord(raw) ?? ({} as Record<string, unknown>);
  let current: unknown = raw;
  for (let i = 0; i < 3; i += 1) {
    const obj = asRecord(current);
    if (!obj) return fallback;
    if (Array.isArray(obj.action_requests)) return obj;
    if (asRecord(obj.value)) {
      current = obj.value;
      continue;
    }
    break;
  }
  return fallback;
}

function normalizeAskQuestion(
  item: Record<string, unknown>,
): AskQuestion | null {
  const question =
    typeof item.question === "string"
      ? item.question
      : typeof item.prompt === "string"
      ? item.prompt
      : typeof item.text === "string"
      ? item.text
      : "";
  if (!question.trim()) return null;
  return {
    question,
    header: typeof item.header === "string" ? item.header : undefined,
    multi_select: item.multi_select === true,
    options: Array.isArray(item.options)
      ? item.options
          .filter((opt): opt is Record<string, unknown> =>
            Boolean(asRecord(opt)),
          )
          .map((opt) => ({
            label: typeof opt.label === "string" ? opt.label : "",
            description:
              typeof opt.description === "string" ? opt.description : undefined,
          }))
          .filter((opt) => opt.label)
      : [],
  };
}

/** Parse a `questions` array from tool args or a HITL interrupt value. */
export function questionsFromUnknown(raw: unknown): AskQuestion[] {
  const parsed = parseJsonObject(raw);
  if (Array.isArray(parsed)) {
    return parsed
      .map((item) => asRecord(item))
      .filter((item): item is Record<string, unknown> => item !== null)
      .map(normalizeAskQuestion)
      .filter((item): item is AskQuestion => item !== null);
  }
  const obj = asRecord(parsed);
  if (!obj) return [];
  if (obj.questions !== undefined) return questionsFromUnknown(obj.questions);
  const single = normalizeAskQuestion(obj);
  return single ? [single] : [];
}

/** Extract the `questions` payload from an `ask_user_question` pause. */
export function extractAskQuestions(
  actions: HitlActionRequest[] | undefined,
): AskQuestion[] {
  if (!actions?.length) return [];
  for (const action of actions) {
    if (action.name !== ASK_USER_TOOL_NAME) continue;
    const args = parseActionArgs(action.args);
    const questions = questionsFromUnknown(args.questions ?? args);
    if (questions.length > 0) return questions;
  }
  return [];
}

export function isAskHitl(actions: HitlActionRequest[] | undefined): boolean {
  return Boolean(actions?.some((a) => a.name === ASK_USER_TOOL_NAME));
}

/** True when this pause collects a secret via the masked card. */
export function isSecretInputHitl(
  actions: HitlActionRequest[] | undefined,
): boolean {
  return Boolean(
    actions?.some((a) => a.name === REQUEST_SECRET_INPUT_TOOL_NAME),
  );
}

/** Extract the slot/prompt/title from a `request_secret_input` pause. */
export function extractSecretInputRequest(
  actions: HitlActionRequest[] | undefined,
): SecretInputRequest | null {
  for (const action of actions ?? []) {
    if (action.name !== REQUEST_SECRET_INPUT_TOOL_NAME) continue;
    const args = parseActionArgs(action.args);
    const slot = typeof args.slot === "string" ? args.slot.trim() : "";
    if (!slot) continue;
    return {
      slot,
      prompt: typeof args.prompt === "string" ? args.prompt : "",
      title:
        typeof args.title === "string" && args.title.trim()
          ? args.title
          : undefined,
    };
  }
  return null;
}

/** True when this pause collects values through the secure-form modal. */
export function isSecureFormHitl(
  actions: HitlActionRequest[] | undefined,
): boolean {
  return Boolean(
    actions?.some((a) => a.name === REQUEST_SECURE_FORM_TOOL_NAME),
  );
}

/**
 * Extract launcher display data from a `request_secure_form` pause.
 *
 * Only the model-authored title/prompt and the field count — the modal's
 * fields and destination banner always come from the server GET record.
 */
export function extractSecureFormRequest(
  actions: HitlActionRequest[] | undefined,
): SecureFormLauncherRequest | null {
  for (const action of actions ?? []) {
    if (action.name !== REQUEST_SECURE_FORM_TOOL_NAME) continue;
    const args = parseActionArgs(action.args);
    const fields = Array.isArray(args.fields) ? args.fields : [];
    return {
      title:
        typeof args.title === "string" && args.title.trim()
          ? args.title
          : undefined,
      prompt: typeof args.prompt === "string" ? args.prompt : "",
      fieldCount: fields.length,
    };
  }
  return null;
}
