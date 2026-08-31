/**
 * Prefer agent custom description for chat welcome subtitle; fall back to
 * template ``welcome_message`` when description is missing / blank.
 */
export function resolveWelcomeSuffix(
  description: string | null | undefined,
  welcomeMessage: string | null | undefined,
): string | null {
  const desc = (description ?? "").trim();
  if (desc) return desc;
  const welcome = (welcomeMessage ?? "").trim();
  return welcome || null;
}
