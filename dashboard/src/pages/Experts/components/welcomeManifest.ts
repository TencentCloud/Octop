import type { LocalizedText } from "@/utils/localizedText";

export interface QuickPrompt {
  title: LocalizedText;
  description: LocalizedText;
  prompt: LocalizedText;
  color: string;
  icon_name: string | null;
}

export interface WelcomeConfigData {
  welcome_message?: LocalizedText;
  quick_prompts: QuickPrompt[];
}

export type WelcomeManifestStatus = "loading" | "ready" | "error";

export interface WelcomeManifestSnapshot {
  status: WelcomeManifestStatus;
  dirty: boolean;
  data: WelcomeConfigData;
}

/** Only persist page config after a successful load, and only if the user edited it. */
export function shouldWriteWelcomeManifest(
  status: WelcomeManifestStatus,
  dirty: boolean,
): boolean {
  return status === "ready" && dirty;
}

export function parseManifestObject(
  raw: string,
): { ok: true; value: Record<string, unknown> } | { ok: false } {
  const text = raw.trim();
  if (!text) return { ok: true, value: {} };
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { ok: true, value: parsed as Record<string, unknown> };
    }
  } catch {
    /* invalid JSON */
  }
  return { ok: false };
}

function hasWelcomeText(message: LocalizedText | undefined): boolean {
  return Boolean(message?.zh?.trim() || message?.en?.trim());
}

export function filterQuickPrompts(prompts: QuickPrompt[]): QuickPrompt[] {
  return prompts.filter(
    (p) => p.title?.zh || p.title?.en || p.prompt?.zh || p.prompt?.en,
  );
}

export function normalizeQuickPrompts(
  prompts:
    | Array<{
        title?: LocalizedText;
        description?: LocalizedText;
        prompt?: LocalizedText;
        color?: string;
        icon_name?: string | null;
      }>
    | undefined,
): QuickPrompt[] {
  return (prompts ?? []).map((prompt) => ({
    title: { zh: prompt.title?.zh ?? "", en: prompt.title?.en ?? "" },
    description: {
      zh: prompt.description?.zh ?? "",
      en: prompt.description?.en ?? "",
    },
    prompt: { zh: prompt.prompt?.zh ?? "", en: prompt.prompt?.en ?? "" },
    color: prompt.color || "#e8f4ff",
    icon_name: prompt.icon_name ?? null,
  }));
}

export function serializeQuickPrompts(prompts: QuickPrompt[]): QuickPrompt[] {
  return filterQuickPrompts(prompts).map((prompt) => ({
    title: { zh: prompt.title?.zh ?? "", en: prompt.title?.en ?? "" },
    description: {
      zh: prompt.description?.zh ?? "",
      en: prompt.description?.en ?? "",
    },
    prompt: { zh: prompt.prompt?.zh ?? "", en: prompt.prompt?.en ?? "" },
    color: prompt.color || "#e8f4ff",
    icon_name: prompt.icon_name ?? null,
  }));
}

/** Merge welcome fields into an existing workspace manifest without dropping other keys. */
export function mergeWelcomeIntoManifest(
  existing: Record<string, unknown>,
  patch: WelcomeConfigData,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...existing };
  if (patch.welcome_message !== undefined) {
    if (hasWelcomeText(patch.welcome_message)) {
      next.welcome_message = {
        zh: patch.welcome_message?.zh ?? "",
        en: patch.welcome_message?.en ?? "",
      };
    } else {
      delete next.welcome_message;
    }
  }
  next.quick_prompts = filterQuickPrompts(patch.quick_prompts);
  return next;
}
