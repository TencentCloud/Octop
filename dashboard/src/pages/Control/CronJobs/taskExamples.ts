import type { CronTaskExamples } from "../../../api/modules/cronjob";
import type { UiLocale } from "../../../utils/locale";

/** Two columns only when there is a full six-card set (desktop). */
export function taskExampleColumns(count: number): 1 | 2 {
  return count >= 6 ? 2 : 1;
}

/** Display contract: 1–3 stay as-is, 4–5 truncate to 3, extras cap at 6. */
export function normalizeTaskExampleCount(items: string[]): string[] {
  if (items.length <= 3) return items;
  if (items.length <= 5) return items.slice(0, 3);
  return items.slice(0, 6);
}

/** Pick locale strings from manifest ``task_examples``; ``null`` means use defaults. */
export function resolveTaskExamples(
  payload: CronTaskExamples | null | undefined,
  locale: UiLocale,
  defaults: string[],
): string[] {
  if (payload == null) return defaults;
  const primary = locale === "zh" ? payload.zh : payload.en;
  const fallback = locale === "zh" ? payload.en : payload.zh;
  const picked = _nonEmpty(primary) ?? _nonEmpty(fallback) ?? [];
  return normalizeTaskExampleCount(picked);
}

function _nonEmpty(items: string[] | undefined): string[] | null {
  if (!items) return null;
  const cleaned = items.map((item) => item.trim()).filter(Boolean);
  return cleaned.length > 0 ? cleaned : null;
}
