import { useMemo } from "react";
import type { ResolvedModel, TokenUsage } from "../../../api/types";
import { modelOptionValue, modelRef } from "../../../utils/modelOptions";
import type { ChatMessage } from "./useChat";

const DEFAULT_MAX = 128_000;

function usageContextInput(
  usage: TokenUsage | null | undefined,
): number | null {
  if (!usage) return null;
  // Prefer last model-call size (context fullness), not turn-summed billing.
  const last = usage.last_input_tokens;
  if (typeof last === "number" && last > 0) return last;
  if (typeof usage.input_tokens === "number" && usage.input_tokens > 0) {
    return usage.input_tokens;
  }
  return null;
}

function modelContextWindow(m: ResolvedModel | undefined): number | null {
  if (!m) return null;
  const window =
    m.context_window ?? m.contextWindow ?? m.max_input_tokens ?? null;
  return window && window > 0 ? window : null;
}

function findModelWindow(
  availableModels: ResolvedModel[],
  ref: string | null | undefined,
): number | null {
  const key = (ref || "").trim();
  if (!key) return null;
  const match = availableModels.find((m) => modelOptionValue(m) === key);
  return modelContextWindow(match);
}

export function useChatContextWindow(
  messages: ChatMessage[],
  contextUsage: TokenUsage | null | undefined,
  selectedModel: string | null,
  availableModels: ResolvedModel[],
  agentDefaultModel?: string | null,
  /** Global preferred model (settings active-model) used when composer is Auto. */
  activeModelRef?: string | null,
) {
  const contextMaxTokens = useMemo(() => {
    const fromSelected = findModelWindow(availableModels, selectedModel);
    if (fromSelected != null) return fromSelected;

    const fromAgent = findModelWindow(availableModels, agentDefaultModel);
    if (fromAgent != null) return fromAgent;

    const fromActive = findModelWindow(availableModels, activeModelRef);
    if (fromActive != null) return fromActive;

    // AUTO with no settings row yet — same order as resolve_first_model_ref.
    const first = availableModels[0];
    const fromFirst = modelContextWindow(first);
    if (fromFirst != null) return fromFirst;

    return DEFAULT_MAX;
  }, [selectedModel, availableModels, agentDefaultModel, activeModelRef]);

  const contextUsedTokens = useMemo(() => {
    const fromStream = usageContextInput(contextUsage);
    if (fromStream != null) return fromStream;
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const fromMsg = usageContextInput(messages[i].usage);
      if (fromMsg != null) return fromMsg;
    }
    return null;
  }, [contextUsage, messages]);

  return { contextMaxTokens, contextUsedTokens };
}

/** Build ``provider/model`` ref from an active-model API payload. */
export function activeModelToRef(
  active: { provider_name?: string; model?: string } | null | undefined,
): string | null {
  const provider = (active?.provider_name || "").trim();
  const model = (active?.model || "").trim();
  if (!provider || !model) return null;
  return modelRef(provider, model);
}
