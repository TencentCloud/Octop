import type { TFunction } from "i18next";
import type { ReasoningCapability } from "../../../api/types/provider";
import type { ModelWireApi } from "./useProviders";
import { formatTokenCount } from "./modelMeta";

export interface WizardModelSource {
  id: string;
  name: string;
  max_input_tokens?: number | null;
  context_window?: number | null;
  max_tokens?: number | null;
  max_output_tokens?: number | null;
  input?: string[];
  reasoning?: boolean | null;
  reasoning_config?: ReasoningCapability | null;
  wire_api?: ModelWireApi | null;
  endpoint_base_url?: string | null;
  native_tool_search?: boolean | null;
  options?: Record<string, unknown> | null;
  description?: string | null;
}

export interface WizardModelDisplayMeta {
  input: string[];
  reasoning?: boolean;
  context_window?: number | null;
  max_tokens?: number | null;
  description?: string;
}

function inferInputModalities(id: string, explicit?: string[]): string[] {
  const lower = id.toLowerCase();
  const input = new Set(explicit?.length ? explicit : ["text"]);
  if (!input.has("text")) input.add("text");
  if (
    lower.includes("-vl") ||
    lower.includes("vision") ||
    lower.includes("-image")
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
  const reasoning =
    model.reasoning_config?.supported === true ||
    inferReasoning(model.id, model.reasoning);

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
    max_tokens: model.max_output_tokens ?? model.max_tokens ?? null,
    description,
  };
}
