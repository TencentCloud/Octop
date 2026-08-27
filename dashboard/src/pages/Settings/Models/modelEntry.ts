import type { ProviderModel } from "./useProviders";

/** Build a model row from the editor while preserving non-editable metadata. */
export function buildProviderModelEntry(
  values: Record<string, unknown>,
  options: { existing?: ProviderModel; isOnnx: boolean },
): ProviderModel {
  const { existing, isOnnx } = options;
  const id = (values.id as string).trim();
  const name = (values.name as string | undefined)?.trim() || id;
  const embedding = isOnnx || values.embedding === true;
  const entry: ProviderModel = existing
    ? { ...existing, id, name }
    : {
        id,
        name,
        enabled: true,
        input: ["text"],
        thinking: null,
      };

  if (embedding) {
    entry.embedding = true;
    entry.task = "embedding";
    // Chat-only fields are editable metadata, so switching to embedding clears
    // them while opaque provider-specific fields remain on the spread object.
    delete entry.context_window;
    delete entry.max_tokens;
    delete entry.max_output_tokens;
    delete entry.reasoning;
    delete entry.reasoning_config;
    return entry;
  }

  delete entry.embedding;
  delete entry.task;
  entry.input = (values.input as string[] | undefined) || ["text"];

  delete entry.context_window;
  if (values.context_window != null) {
    entry.context_window = values.context_window as number;
  }

  // max_output_tokens is the preset/probe alias; editor saves the canonical
  // provider-row field and removes a stale alias when the visible value changes.
  delete entry.max_tokens;
  delete entry.max_output_tokens;
  if (values.max_tokens != null) {
    entry.max_tokens = values.max_tokens as number;
  }

  delete entry.reasoning;
  delete entry.reasoning_config;
  if (values.reasoning != null) {
    entry.reasoning = values.reasoning as boolean;
  }
  if (values.reasoning === true) {
    const efforts = (values.reasoning_efforts as string[] | undefined) || [];
    entry.reasoning_config = {
      supported: true,
      toggle: values.reasoning_toggle !== false,
      default_mode:
        (values.reasoning_default_mode as "auto" | "enabled" | "disabled") ||
        "auto",
      efforts,
      default_effort:
        (values.reasoning_default_effort as string | undefined) || null,
      effort_type:
        (values.reasoning_effort_type as "enum" | "token_budget") || "enum",
      adapter:
        (values.reasoning_adapter as
          | "status_only"
          | "thinking"
          | "thinking_nested_effort"
          | "openai_reasoning_effort"
          | "anthropic_adaptive"
          | "anthropic_budget"
          | "dashscope"
          | "openrouter") || "thinking",
    };
  }

  return entry;
}
