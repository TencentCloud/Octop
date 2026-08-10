/** Always keep default_open connectors in the composer selection. */
export function withDefaultOpenConnectors(
  selected: string[],
  defaults: string[],
): string[] {
  const next = [...selected];
  for (const name of defaults) {
    if (!next.includes(name)) next.push(name);
  }
  return next;
}
