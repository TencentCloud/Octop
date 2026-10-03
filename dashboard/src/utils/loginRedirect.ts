/** Return an internal destination, never an absolute or protocol-relative URL. */
export function safeRedirect(path: string | null): string {
  if (
    !path ||
    !path.startsWith("/") ||
    [...path].some(
      (char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127,
    ) ||
    path.startsWith("//") ||
    path.includes("\\") ||
    path.includes("://") ||
    path.startsWith("http:") ||
    /^\/login\/?(?:[?#]|$)/.test(path)
  ) {
    return "/chat";
  }
  return path;
}
