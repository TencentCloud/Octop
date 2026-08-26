export function normalizeKnowledgePath(raw: string | null | undefined): string {
  const parts = String(raw ?? "")
    .replaceAll("\\", "/")
    .split("/")
    .map((part) => part.trim())
    .filter((part) => part && part !== ".");
  if (parts.some((part) => part === "..")) {
    throw new Error("invalid knowledge path");
  }
  return parts.join("/");
}

export function knowledgeBasename(path: string): string {
  const normalized = normalizeKnowledgePath(path);
  if (!normalized) return "";
  const parts = normalized.split("/");
  return parts[parts.length - 1] ?? "";
}

export function joinKnowledgePath(prefix: string, name: string): string {
  const parent = normalizeKnowledgePath(prefix);
  const child = knowledgeBasename(name) || normalizeKnowledgePath(name);
  if (!child) return parent;
  return parent ? `${parent}/${child}` : child;
}

export function isDirectKnowledgeChild(path: string, prefix: string): boolean {
  const normalized = normalizeKnowledgePath(path);
  const parent = normalizeKnowledgePath(prefix);
  if (!normalized || normalized === parent) return false;
  if (!parent) return !normalized.includes("/");
  if (!normalized.startsWith(`${parent}/`)) return false;
  const rest = normalized.slice(parent.length + 1);
  return Boolean(rest) && !rest.includes("/");
}

export function shouldOpenKnowledgeFolder(
  isDir: boolean,
  event?: { target?: EventTarget | null },
): boolean {
  if (!isDir) return false;
  const target = event?.target;
  if (target instanceof Element && target.closest("[data-kb-doc-actions]")) {
    return false;
  }
  return true;
}

export function knowledgeBreadcrumb(
  prefix: string,
  rootLabel: string,
): { label: string; path: string }[] {
  const normalized = normalizeKnowledgePath(prefix);
  const segments = [{ label: rootLabel, path: "" }];
  if (!normalized) return segments;
  const parts = normalized.split("/");
  let acc = "";
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part;
    segments.push({ label: part, path: acc });
  }
  return segments;
}
