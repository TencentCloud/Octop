/** Translate agent ``last_error`` values stored with an ``octop:`` prefix. */

import type { TFunction } from "i18next";

const MODEL_CONFIG_KEYS = new Set([
  "octop:agent_errors.no_models_configured",
  "octop:agent_errors.model_ref_unavailable",
]);

function isRawModelRefError(error: string): boolean {
  const lower = error.toLowerCase();
  return (
    lower.includes("unknown provider") ||
    lower.includes("not found or disabled") ||
    lower.includes("has no model") ||
    lower.includes("malformed model ref") ||
    lower.includes("default_model=") ||
    (lower.includes(" is disabled") && lower.includes("model")) ||
    (lower.includes("must be in the form") && lower.includes("model"))
  );
}

function isRawNoModelsError(error: string): boolean {
  const lower = error.toLowerCase();
  return (
    lower.includes("enabled models") ||
    lower.includes("requires providers") ||
    lower.includes("model_factory") ||
    lower.includes("no provider") ||
    lower.includes("no models")
  );
}

export function isAgentModelConfigError(
  error: string | null | undefined,
): boolean {
  if (!error) return false;
  if (MODEL_CONFIG_KEYS.has(error)) return true;
  return isRawNoModelsError(error) || isRawModelRefError(error);
}

export function formatAgentError(
  error: string | null | undefined,
  t: TFunction,
): string {
  if (!error) return "";
  if (error.startsWith("octop:")) {
    const key = error.slice("octop:".length);
    return t(key, { defaultValue: error });
  }
  if (isRawModelRefError(error)) {
    return t("agent_errors.model_ref_unavailable");
  }
  if (isRawNoModelsError(error)) {
    return t("agent_errors.no_models_configured");
  }
  return error;
}

/** Expert harness runtime is loaded (`running`); not storage-backend config. */
export function isAgentChatReady(state: string | null | undefined): boolean {
  return state === "running";
}

/** Agent exists but harness runtime is not loaded (user stopped or never started). */
export function isAgentStopped(state: string | null | undefined): boolean {
  return state === "stopped" || state === "created";
}

export function isAgentFailed(state: string | null | undefined): boolean {
  return state === "failed" || state === "error";
}

export function formatAgentState(state: string, t: TFunction): string {
  return t(`common.agentState.${state}`, { defaultValue: state });
}
