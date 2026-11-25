/**
 * Localised labels for built-in agent tools shown in chat message bubbles.
 * Labels are defined in backend ``src/octop/i18n/*.json`` (``tools.*``).
 */

import { useTranslation } from "react-i18next";
import { isFileToolName } from "../constants";

/** Names the harness invents when an ACP update did not include a title. */
export function isPlaceholderToolName(name?: string): boolean {
  const text = name?.trim().toLowerCase();
  return !text || text === "unknown";
}

/** Keep a real tool name. A later ``unknown`` update must not replace it.

ACP file edits are stored as ``write_file`` / ``edit_file`` and then again
under the agent title (``Write /path``). The file card only recognizes the
native name, so that title must not replace it.
*/
export function preferToolName(
  incoming?: string,
  current?: string,
): string | undefined {
  const next = incoming?.trim();
  const prev = current?.trim();
  if (isFileToolName(prev) && !isFileToolName(next)) return prev;
  if (!isPlaceholderToolName(next)) return next;
  return prev || next;
}

export function useToolDisplayNames(): (name?: string) => string {
  const { t, i18n } = useTranslation();

  return (name?: string) => {
    const raw = name?.trim();
    if (!raw) return t("tools.unknown", "unknown");
    const key = `tools.${raw}`;
    // No catalog entry: show the name the tool already used.
    if (!i18n.exists(key)) return raw;
    const translated = t(key);
    return translated === key ? raw : translated;
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
