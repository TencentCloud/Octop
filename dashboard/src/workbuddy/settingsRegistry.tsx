import { lazy, type ComponentType } from "react";
import {
  canAccessKeys,
  type PermissionHolder,
  type PermissionKeys,
  PERM,
} from "../utils/permissions";
const Models = lazy(() => import("../pages/Settings/Models"));
const Usage = lazy(() => import("../pages/Control/TokenUsage"));
const Plugins = lazy(() => import("../pages/Admin/Plugins"));
const Packages = lazy(() => import("../pages/SkillPackages"));
const Bridge = lazy(() => import("../pages/Settings/Bridge"));
const ACP = lazy(() => import("../pages/Agent/ACP"));
const Storage = lazy(() => import("../pages/Admin/Storage"));
const Security = lazy(() => import("../pages/Settings/Security"));
const Users = lazy(() => import("../pages/Admin/Users"));
const Envs = lazy(() => import("../pages/Settings/Environments"));
const Backup = lazy(() => import("../pages/Settings/BackupRestore"));
const Observability = lazy(() =>
  import("../pages/Settings/Observability").then((m) => ({
    default: m.ObservabilitySettingsPanel,
  })),
);
const Https = lazy(() =>
  import("../pages/Settings/HttpsSettings").then((m) => ({
    default: m.HttpsSettingsPanel,
  })),
);
const Updates = lazy(
  () => import("../pages/Settings/AdvancedSettings/UpdateConfig"),
);
const Captcha = lazy(
  () => import("../pages/Settings/AdvancedSettings/CaptchaSettings"),
);
const AgentPanels = lazy(() => import("./AgentSettingsPanel"));
const Shortcuts = lazy(() => import("./SettingsShortcuts"));
const About = lazy(() => import("./SettingsAbout"));
export type SettingsGroup =
  | "general"
  | "features"
  | "security"
  | "management"
  | "about";
export interface SettingsSection {
  id: string;
  label: string;
  group: SettingsGroup;
  permission?: PermissionKeys;
  agentScoped?: boolean;
  Component?: ComponentType;
  agentPanel?: string;
}
export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  { id: "general", label: "workbuddy.settings.general", group: "general" },
  { id: "account", label: "workbuddy.settings.account", group: "general" },
  { id: "appearance", label: "workbuddy.appearance", group: "general" },
  {
    id: "shortcuts",
    label: "workbuddy.settings.shortcuts",
    group: "general",
    Component: Shortcuts,
  },
  { id: "usage", label: "nav.tokenUsage", group: "general", Component: Usage },
  {
    id: "personalization",
    label: "nav.personalization",
    group: "features",
    agentScoped: true,
    agentPanel: "personality",
  },
  {
    id: "memory",
    label: "personalization.tabs.memory",
    group: "features",
    agentScoped: true,
    agentPanel: "memory",
  },
  {
    id: "agent",
    label: "workbuddy.settings.agent",
    group: "features",
    agentScoped: true,
    agentPanel: "config",
  },
  {
    id: "channels",
    label: "nav.channels",
    group: "features",
    permission: PERM.channels,
    agentScoped: true,
    agentPanel: "channels",
  },
  {
    id: "models",
    label: "nav.models",
    group: "features",
    permission: PERM.modelsPage,
    Component: Models,
  },
  {
    id: "tools",
    label: "personalization.tabs.tools",
    group: "features",
    agentScoped: true,
    agentPanel: "tools",
  },
  {
    id: "agent-plugins",
    label: "workbuddy.settings.agentPlugins",
    group: "features",
    agentScoped: true,
    agentPanel: "plugins",
  },
  {
    id: "subagents",
    label: "personalization.tabs.subagents",
    group: "features",
    agentScoped: true,
    agentPanel: "subagents",
  },
  {
    id: "plugins",
    label: "nav.adminPlugins",
    group: "features",
    permission: PERM.plugins,
    Component: Plugins,
  },
  {
    id: "skill-packages",
    label: "nav.skillPackages",
    group: "features",
    permission: PERM.skillPackages,
    Component: Packages,
  },
  { id: "bridge", label: "nav.bridge", group: "features", Component: Bridge },
  {
    id: "acp",
    label: "nav.acp",
    group: "features",
    permission: "admin",
    agentScoped: true,
    Component: ACP,
  },
  {
    id: "storage",
    label: "nav.adminStorage",
    group: "security",
    permission: PERM.storage,
    Component: Storage,
  },
  {
    id: "backup",
    label: "nav.backupRestore",
    group: "security",
    permission: ["backup"],
    Component: Backup,
  },
  {
    id: "security",
    label: "nav.security",
    group: "security",
    permission: PERM.securityPage,
    Component: Security,
  },
  {
    id: "https",
    label: "nav.https",
    group: "security",
    permission: ["tls"],
    Component: Https,
  },
  {
    id: "users",
    label: "nav.adminUsers",
    group: "management",
    permission: PERM.usersPage,
    Component: Users,
  },
  {
    id: "environments",
    label: "nav.environments",
    group: "management",
    permission: ["envs"],
    Component: Envs,
  },
  {
    id: "captcha",
    label: "nav.loginCaptcha",
    group: "management",
    permission: ["captcha"],
    Component: Captcha,
  },
  {
    id: "observability",
    label: "nav.observability",
    group: "management",
    permission: ["observability"],
    Component: Observability,
  },
  {
    id: "updates",
    label: "nav.checkUpdates",
    group: "about",
    permission: ["update"],
    Component: Updates,
  },
  {
    id: "about",
    label: "workbuddy.settings.about",
    group: "about",
    Component: About,
  },
];
export { AgentPanels };
export function allowedSettingsSections(user: PermissionHolder | null) {
  return SETTINGS_SECTIONS.filter(
    (item) => !item.permission || canAccessKeys(user, item.permission),
  );
}
/** Preserve the full query string: existing panel tabs and OAuth callbacks retain their meaning. */
export function legacySettingsPath(
  rawPath: string,
  search: string,
): string | null {
  const path = rawPath.replace(/^\/(?:orca|octop)(?=\/)/, "");
  const params = new URLSearchParams(search);
  const tab = params.get("tab");
  const direct: Record<string, string> = {
    "/admin/models": "models",
    "/admin/users": "users",
    "/admin/backend": "storage",
    "/admin/plugins": "plugins",
    "/admin/security": "security",
    "/token-usage": "usage",
    "/skill-packages": "skill-packages",
    "/bridge": "bridge",
    "/acp": "acp",
    "/agent-config": "agent",
    "/channels": "channels",
    "/models": "models",
    "/admin/shared-models": "models",
    "/admin/storage": "storage",
    "/plugins": "plugins",
    "/updates": "updates",
    "/admin/updates": "updates",
    "/environments": "environments",
    "/advanced-settings": "environments",
    "/admin/agents": "users",
    "/memory": "memory",
    "/mbti": "personalization",
    "/subagents": "subagents",
  };
  let section = direct[path];
  const special = (
    {
      "/admin/voice": ["models", "voice"],
      "/admin/audit": ["security", "audit"],
      "/admin/sso": ["users", "oidc"],
    } as Record<string, [string, string]>
  )[path];
  if (special) {
    params.set("tab", params.get("tab") ?? special[1]);
    return `/settings/${special[0]}?${params}`;
  }
  if (path === "/admin/advanced")
    section =
      (
        {
          observability: "observability",
          backup: "backup",
          https: "https",
          updates: "updates",
          captcha: "captcha",
          voice: "models",
          search: "models",
          bridge: "bridge",
        } as Record<string, string>
      )[tab ?? ""] ?? "environments";
  if (path === "/personalization" || path.startsWith("/personalization/")) {
    const part = path.split("/")[2] ?? "mbti";
    if (part === "skills") {
      params.set("tab", "installed");
      return `/skills?${params}`;
    }
    section = (
      {
        mbti: "personalization",
        memory: "memory",
        channels: "channels",
        tools: "tools",
        plugins: "agent-plugins",
        subagents: "subagents",
        acp: "acp",
      } as Record<string, string>
    )[part];
  }
  return section ? `/settings/${section}${search}` : null;
}
