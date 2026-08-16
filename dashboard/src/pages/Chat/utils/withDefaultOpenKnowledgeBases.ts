/** Always keep default_open knowledge bases in the composer selection. */
export function withDefaultOpenKnowledgeBases(
  selected: string[],
  defaults: string[],
): string[] {
  const next = [...selected];
  for (const id of defaults) {
    if (!next.includes(id)) next.push(id);
  }
  return next;
}
