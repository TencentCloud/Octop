/** Map sidebar paths to their lazy route chunks for hover prefetch. */
const ROUTE_PREFETCHERS: Record<string, () => Promise<unknown>> = {
  "/chat": () => import("../pages/Chat"),
  "/experts": () => import("../pages/Experts"),
  "/tasks": () => import("../pages/Control/CronJobs"),
  "/connectors": () => import("../pages/Agent/Connectors"),
  "/skills": () => import("../pages/Agent/Skills"),
  "/token-usage": () => import("../pages/Control/TokenUsage"),
  "/channels": () => import("../pages/Control/Channels"),
  "/terminal": () => import("../pages/Control/Terminal"),
  "/remote-browser": () => import("../pages/Control/RemoteBrowser"),
  "/remote-desktop": () => import("../pages/Control/RemoteDesktop"),
  "/acp": () => import("../pages/Agent/ACP"),
  "/subagents": () => import("../pages/Control/Subagents"),
  "/mbti": () => import("../pages/Agent/MBTI"),
  "/memory": () => import("../pages/Agent/Memory"),
  "/admin/models": () => import("../pages/Settings/Models"),
  "/admin/users": () => import("../pages/Admin/Users"),
  "/admin/backend": () => import("../pages/Admin/Storage"),
  "/admin/audit": () => import("../pages/Admin/Audit"),
  "/admin/plugins": () => import("../pages/Admin/Plugins"),
  "/admin/security": () => import("../pages/Settings/Security"),
  "/admin/advanced": () => import("../pages/Settings/AdvancedSettings"),
  "/admin/updates": () => import("../pages/Admin/Updates"),
};

export function prefetchRoute(path: string): void {
  const load = ROUTE_PREFETCHERS[path];
  if (load) void load();
}
