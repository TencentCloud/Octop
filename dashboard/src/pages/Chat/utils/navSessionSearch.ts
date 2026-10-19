/** Sidebar search: expert name or conversation title. */

export function normalizeNavQuery(query: string): string {
  return query.trim().toLowerCase();
}

export function matchesNavQuery(text: string, query: string): boolean {
  const q = normalizeNavQuery(query);
  if (!q) return true;
  return text.toLowerCase().includes(q);
}

export function expertVisibleInNavSearch(
  agentName: string,
  sessionNames: readonly string[],
  query: string,
): boolean {
  if (!normalizeNavQuery(query)) return true;
  if (matchesNavQuery(agentName, query)) return true;
  return sessionNames.some((name) => matchesNavQuery(name, query));
}

export function filterSessionNames(
  names: readonly string[],
  query: string,
): string[] {
  if (!normalizeNavQuery(query)) return [...names];
  return names.filter((name) => matchesNavQuery(name, query));
}
