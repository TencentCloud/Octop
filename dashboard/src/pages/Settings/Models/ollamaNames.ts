/** Ollama treats a missing tag as ``:latest``. Do not alias other tags (7b vs 72b). */

export function expandOllamaDownloadedIds(names: readonly string[]): string[] {
  const out = new Set<string>();
  for (const raw of names) {
    const name = raw.trim();
    if (!name) continue;
    out.add(name);
    if (name.endsWith(":latest")) {
      const bare = name.slice(0, -":latest".length);
      if (bare) out.add(bare);
    } else if (!name.includes(":")) {
      out.add(`${name}:latest`);
    }
  }
  return [...out];
}
