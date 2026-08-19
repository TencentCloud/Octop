/** Client-side helpers mirroring backend ``user_has_permission``. */

export type PermissionHolder = {
  role: "admin" | "user" | string;
  permissions?: string[] | null;
};

/** Any-of module keys, or ``"admin"`` for role-only. */
export type PermissionKeys = readonly string[] | "admin";

export const PERM = {
  channels: ["channels"],
  connectors: ["connectors"],
  skillPackages: ["skill_packages"],
  knowledgeBases: ["knowledge_bases"],
  knowledgeSettings: ["knowledge_settings"],
  knowledgeBasesPage: ["knowledge_bases", "knowledge_settings"],
  workbench: ["browser", "terminal"],
  browser: ["browser"],
  terminal: ["terminal"],
  desktop: ["desktop"],
  mobile: ["mobile"],
  usersPage: ["users", "sso"],
  modelsPage: ["providers", "ollama_models", "onnx_models"],
  storage: ["storage_backends"],
  plugins: ["plugins"],
  securityPage: ["security", "admin_console"],
  advancedPage: [
    "voice",
    "update",
    "envs",
    "tls",
    "observability",
    "backup",
    "search",
  ],
} as const satisfies Record<string, readonly string[]>;

/** Sidebar item key → permission keys. Shared with path guards. */
export const NAV_PERMISSIONS = {
  channels: PERM.channels,
  connectors: PERM.connectors,
  "skill-packages": PERM.skillPackages,
  "knowledge-bases": PERM.knowledgeBasesPage,
  workbench: PERM.workbench,
  "remote-desktop": PERM.desktop,
  "remote-android": PERM.mobile,
  acp: "admin",
  "admin-users": PERM.usersPage,
  models: PERM.modelsPage,
  "admin-storage": PERM.storage,
  "admin-plugins": PERM.plugins,
  "admin-security": PERM.securityPage,
  "admin-advanced": PERM.advancedPage,
} as const satisfies Record<string, PermissionKeys>;

export type NavPermissionKey = keyof typeof NAV_PERMISSIONS;

export const USERS_TAB_PERMISSIONS = {
  local: "users",
  sso: "sso",
} as const;

export const ADVANCED_TAB_PERMISSIONS = {
  "env-vars": "envs",
  search: "search",
  voice: "voice",
  observability: "observability",
  backup: "backup",
  https: "tls",
  updates: "update",
} as const;

export const SECURITY_TAB_PERMISSIONS = {
  hitl: "security",
  filesystem: "security",
  pii: "security",
  tool_guard: "security",
  skill_scan: "security",
  audit: "admin_console",
} as const;

/** True when the user may access the module ``key`` (admin bypasses). */
export function userCan(
  user: PermissionHolder | null | undefined,
  key: string,
): boolean {
  if (!user) return false;
  if (user.role === "admin") return true;
  return (user.permissions ?? []).includes(key);
}

/** True when the user holds any of the given keys (admin bypasses). */
export function userCanAny(
  user: PermissionHolder | null | undefined,
  keys: readonly string[],
): boolean {
  if (!user) return false;
  if (user.role === "admin") return true;
  const held = new Set(user.permissions ?? []);
  return keys.some((k) => held.has(k));
}

export function canAccessKeys(
  user: PermissionHolder | null | undefined,
  keys: PermissionKeys,
): boolean {
  if (keys === "admin") return Boolean(user && user.role === "admin");
  return userCanAny(user, keys);
}

export function navAllowed(
  user: PermissionHolder | null | undefined,
  navKey: NavPermissionKey,
): boolean {
  return canAccessKeys(user, NAV_PERMISSIONS[navKey]);
}

export function userCanKey(
  user: PermissionHolder | null | undefined,
  key: string | readonly string[],
): boolean {
  return typeof key === "string" ? userCan(user, key) : userCanAny(user, key);
}

/**
 * Permissions that unlock a dashboard path (any-of).
 * ``"admin"`` means role===admin only (no module key this round).
 * ``null`` means no special gate.
 */
export function pathPermissionKeys(pathname: string): PermissionKeys | null {
  if (pathname.startsWith("/admin/users") || pathname === "/admin/sso") {
    return PERM.usersPage;
  }
  if (pathname.startsWith("/admin/models") || pathname === "/models") {
    return PERM.modelsPage;
  }
  if (pathname.startsWith("/admin/backend")) {
    return PERM.storage;
  }
  if (
    pathname.startsWith("/admin/plugins") ||
    pathname === "/plugins" ||
    pathname.startsWith("/plugins/")
  ) {
    return PERM.plugins;
  }
  if (
    pathname.startsWith("/admin/security") ||
    pathname.startsWith("/admin/audit")
  ) {
    return PERM.securityPage;
  }
  if (
    pathname.startsWith("/admin/advanced") ||
    pathname.startsWith("/admin/voice") ||
    pathname.startsWith("/admin/updates")
  ) {
    return PERM.advancedPage;
  }
  if (pathname.startsWith("/admin/")) {
    return "admin";
  }
  if (
    pathname === "/personalization/channels" ||
    pathname === "/channels" ||
    pathname.startsWith("/personalization/channels/")
  ) {
    return PERM.channels;
  }
  if (pathname === "/connectors" || pathname.startsWith("/connectors/")) {
    return PERM.connectors;
  }
  if (
    pathname === "/skill-packages" ||
    pathname.startsWith("/skill-packages/")
  ) {
    return PERM.skillPackages;
  }
  if (
    pathname === "/knowledge-bases" ||
    pathname.startsWith("/knowledge-bases/")
  ) {
    return PERM.knowledgeBasesPage;
  }
  if (
    pathname === "/remote-desktop" ||
    pathname.startsWith("/remote-desktop/")
  ) {
    return PERM.desktop;
  }
  if (
    pathname === "/remote-android" ||
    pathname.startsWith("/remote-android/")
  ) {
    return PERM.mobile;
  }
  if (pathname === "/workbench/terminal" || pathname === "/terminal") {
    return PERM.terminal;
  }
  if (pathname === "/workbench/browser" || pathname === "/remote-browser") {
    return PERM.browser;
  }
  if (pathname === "/workbench" || pathname.startsWith("/workbench/")) {
    return PERM.workbench;
  }
  if (pathname === "/acp" || pathname.startsWith("/acp/")) {
    return "admin";
  }
  return null;
}

/** True when this route config path should be wrapped in RequirePermission. */
export function routeNeedsPermission(routePath: string): boolean {
  const probe = routePath.replace(/\/\*$/, "").replace(/\/:[^/]+/g, "");
  if (pathPermissionKeys(probe) !== null) return true;
  if (probe === "/personalization" || probe.startsWith("/personalization/")) {
    return true;
  }
  if (probe === "/workbench" || probe.startsWith("/workbench/")) return true;
  if (probe.startsWith("/admin")) return true;
  return false;
}

export function canAccessPath(
  user: PermissionHolder | null | undefined,
  pathname: string,
): boolean {
  const req = pathPermissionKeys(pathname);
  if (req === null) return true;
  return canAccessKeys(user, req);
}
