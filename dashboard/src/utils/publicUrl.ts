/**
 * Resolve a path under the Vite-configured public base (``import.meta.env.BASE_URL``).
 * Use for static assets and SW registration when the app may be hosted under a subpath.
 */
export function publicUrl(path: string): string {
  const base = import.meta.env.BASE_URL || "/";
  const cleaned = path.replace(/^\//, "");
  if (base === "/") return `/${cleaned}`;
  const prefix = base.endsWith("/") ? base : `${base}/`;
  return `${prefix}${cleaned}`;
}

/** Router basename: no trailing slash; ``undefined`` when served from domain root. */
export function routerBasename(): string | undefined {
  const base = import.meta.env.BASE_URL || "/";
  if (base === "/") return undefined;
  return base.replace(/\/$/, "") || undefined;
}
