import { useMemo } from "react";
import type { ResolvedModel, TokenUsage } from "../../../api/types";
import { modelOptionValue } from "../../../utils/modelOptions";
import type { ChatMessage } from "./useChat";

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

export function useChatContextWindow(
  messages: ChatMessage[],
  contextUsage: TokenUsage | null | undefined,
  selectedModel: string | null,
  availableModels: ResolvedModel[],
  agentDefaultModel?: string | null,
) {
  const contextMaxTokens = useMemo(() => {
    if (selectedModel) {
      const match = availableModels.find(
        (m) => modelOptionValue(m) === selectedModel,
      );
      const window = match?.context_window ?? match?.contextWindow;
      if (window && window > 0) return window;
    }
    if (agentDefaultModel) {
      const match = availableModels.find(
        (m) => modelOptionValue(m) === agentDefaultModel,
      );
      const window = match?.context_window ?? match?.contextWindow;
      if (window && window > 0) return window;
    }
    return 128_000;
  }, [selectedModel, availableModels, agentDefaultModel]);

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
