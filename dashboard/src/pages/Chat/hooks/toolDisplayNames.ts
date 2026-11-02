/**
 * Localised labels for built-in agent tools shown in chat message bubbles.
 * Labels are defined in backend ``src/octop/i18n/*.json`` (``tools.*``).
 */

import { useTranslation } from "react-i18next";

export function useToolDisplayNames(): (name?: string) => string {
  const { t } = useTranslation();

  return (name?: string) => {
    if (!name) return t("tools.unknown", "unknown");
    const key = `tools.${name}`;
    const translated = t(key);
    return translated === key ? name : translated;
  };
}

const DEFERRED_TOOL = "call_deferred_tool";

function toolBaseName(name: string): string {
  const slash = name.lastIndexOf("/");
  return (slash >= 0 ? name.slice(slash + 1) : name).trim();
}

/** Tool id inside ``call_deferred_tool`` arguments, including a partial JSON stream. */
export function deferredCallTargetName(args: unknown): string | null {
  if (typeof args === "string") {
    const match = /"name"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(args);
    const raw = match?.[1]?.replace(/\\"/g, '"').replace(/\\\\/g, "\\").trim();
    return raw || null;
  }
  if (!args || typeof args !== "object" || Array.isArray(args)) return null;
  const name = (args as { name?: unknown }).name;
  if (typeof name !== "string") return null;
  const trimmed = name.trim();
  return trimmed || null;
}

/**
 * ``call_deferred_tool`` only forwards another tool. Show that tool's label
 * once its name is present; otherwise the caller keeps the wrapper label.
 */
export function resolveDeferredToolLabel(
  toolName: string | undefined,
  args: unknown,
  translate: (name?: string) => string,
): string | null {
  if (!toolName || toolBaseName(toolName) !== DEFERRED_TOOL) return null;
  const target = deferredCallTargetName(args);
  if (!target || toolBaseName(target) === DEFERRED_TOOL) return null;
  return translate(target);
}

/** Resolve a display label when the stream chunk already carries ``display_name``. */
export function resolveToolLabel(
  name: string | undefined,
  displayName: string | undefined,
  translate: (name?: string) => string,
): string {
  if (displayName?.trim()) return displayName;
  return translate(name);
}
