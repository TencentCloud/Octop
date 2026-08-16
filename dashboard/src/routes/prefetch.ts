/** Map sidebar paths to their lazy route chunks for hover prefetch. */
const ROUTE_PREFETCHERS: Record<string, () => Promise<unknown>> = {
  "/chat": () => import("../pages/Chat"),
  "/experts": () => import("../pages/Experts"),
  "/tasks": () => import("../pages/Control/CronJobs"),
  "/connectors": () => import("../pages/Agent/Connectors"),
  "/skill-packages": () => import("../pages/SkillPackages"),
  "/knowledge-bases": () => import("../pages/KnowledgeBases"),
  "/skills": () => import("../pages/Agent/Personalization"),
  "/token-usage": () => import("../pages/Control/TokenUsage"),
  "/channels": () => import("../pages/Agent/Personalization"),
  "/workbench": () => import("../pages/Control/Workbench"),
  "/workbench/browser": () => import("../pages/Control/Workbench"),
  "/workbench/terminal": () => import("../pages/Control/Workbench"),
  "/remote-desktop": () => import("../pages/Control/RemoteDesktop"),
  "/acp": () => import("../pages/Agent/ACP"),
  "/personalization": () => import("../pages/Agent/Personalization"),
  "/personalization/skills": () => import("../pages/Agent/Personalization"),
  "/personalization/subagents": () => import("../pages/Agent/Personalization"),
  "/personalization/channels": () => import("../pages/Agent/Personalization"),
  "/personalization/mbti": () => import("../pages/Agent/Personalization"),
  "/personalization/memory": () => import("../pages/Agent/Personalization"),
  "/subagents": () => import("../pages/Agent/Personalization"),
  "/mbti": () => import("../pages/Agent/Personalization"),
  "/memory": () => import("../pages/Agent/Personalization"),
  "/admin/models": () => import("../pages/Settings/Models"),
  "/admin/users": () => import("../pages/Admin/Users"),
  "/admin/backend": () => import("../pages/Admin/Storage"),
  "/admin/plugins": () => import("../pages/Admin/Plugins"),
  "/admin/security": () => import("../pages/Settings/Security"),
  "/admin/advanced": () => import("../pages/Settings/AdvancedSettings"),
  "/agent-config": () => import("../pages/Agent/Config"),
};

export function prefetchRoute(path: string): void {
  const load = ROUTE_PREFETCHERS[path];
  if (load) void load();
}
