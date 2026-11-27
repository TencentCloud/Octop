import type { TFunction } from "i18next";
import { formatTokenCount } from "./modelMeta";

export interface WizardModelSource {
  id: string;
  name: string;
  max_input_tokens?: number | null;
  context_window?: number | null;
  max_tokens?: number | null;
  input?: string[];
  reasoning?: boolean | null;
  description?: string | null;
}

export interface WizardModelDisplayMeta {
  input: string[];
  reasoning?: boolean;
  context_window?: number | null;
  max_tokens?: number | null;
  description?: string;
}

// Match `vl` as a standalone token (`qwen2.5-vl`, `qwen-vl-max`, `qwen3-vl2`)
// without matching unrelated words that start with `vl` such as `-vllm`.
const VISION_VL_RE = /(?:^|[-_/])vl(?=$|[-_/\d])/;

export function inferInputModalities(
  id: string,
  explicit?: string[],
): string[] {
  const cleaned = (explicit ?? [])
    .map((m) => m.trim().toLowerCase())
    .filter(Boolean);
  if (cleaned.length > 0) {
    const input = new Set(cleaned);
    if (!input.has("text")) input.add("text");
    return [...input];
  }
  const lower = id.trim().toLowerCase();
  const input = new Set<string>(["text"]);
  if (
    VISION_VL_RE.test(lower) ||
    lower.includes("vision") ||
    lower.includes("-image") ||
    lower.includes("gpt-4o") ||
    lower.includes("gpt-4.1") ||
    lower.includes("claude-3") ||
    lower.includes("gemini")
  ) {
    input.add("image");
  }
  if (lower.includes("audio") || lower.includes("whisper")) {
    input.add("audio");
  }
  return [...input];
}

function inferReasoning(id: string, explicit?: boolean | null): boolean {
  if (explicit) return true;
  const lower = id.toLowerCase();
  return (
    lower.includes("reasoner") ||
    lower.includes("thinking") ||
    /\bo[134](-|$)/.test(lower)
  );
}

export function enrichWizardModel(
  model: WizardModelSource,
  t: TFunction,
): WizardModelDisplayMeta {
  const context = model.context_window ?? model.max_input_tokens ?? null;
  const input = inferInputModalities(model.id, model.input);
  const reasoning = inferReasoning(model.id, model.reasoning);

  let description = model.description?.trim() || undefined;
  if (!description) {
    if (reasoning) {
      description = t("wizard.model.hintReasoning");
    } else if (input.includes("image") && input.length > 1) {
      description = t("wizard.model.hintMultimodal");
    } else if (context) {
      description = t("wizard.model.hintContext", {
        value: formatTokenCount(context),
      });
    } else {
      description = t("wizard.model.hintDefault");
    }
  }

  return {
    input,
    reasoning: reasoning || undefined,
    context_window: context,
    max_tokens: model.max_tokens ?? null,
    description,
  };
}
