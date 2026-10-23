import type { SidebarNavLayout } from "../../../layouts/sidebarNavLayout";
import { builtinNavGroupLabelKey } from "../../../layouts/sidebarNav";

/**
 * Sidebar item → permission chips, in tab order.
 * One chip stays flat; several sit under that nav item.
 * Chat stays visible and is not a permission. Experts, tasks, and token usage are.
 * `knowledge_settings` belongs with Knowledge, matching the page gate.
 */
const NAV_PERMISSION_CHIPS: readonly {
  key: string;
  labelKey: string;
  permissions: readonly string[];
  /** Stay in the parent nav group as chips, beside siblings such as Channels. */
  inline?: boolean;
}[] = [
  { key: "chat", labelKey: "nav.chat", permissions: [] },
  { key: "experts", labelKey: "nav.experts", permissions: ["experts"] },
  { key: "tasks", labelKey: "nav.tasks", permissions: ["tasks"] },
  {
    key: "token-usage",
    labelKey: "nav.tokenUsage",
    permissions: ["token_usage"],
  },
  {
    key: "personalization",
    labelKey: "nav.personalization",
    inline: true,
    permissions: [
      "skills",
      "subagents",
      "tools",
      "agent_plugins",
      "mbti",
      "memory",
    ],
  },
  { key: "channels", labelKey: "nav.channels", permissions: ["channels"] },
  {
    key: "connectors",
    labelKey: "nav.connectors",
    permissions: ["connectors"],
  },
  {
    key: "skill-packages",
    labelKey: "nav.skillPackages",
    permissions: ["skill_packages"],
  },
  {
    key: "knowledge-bases",
    labelKey: "nav.knowledgeBases",
    permissions: ["knowledge_bases", "knowledge_settings"],
  },
  {
    key: "bridge",
    labelKey: "nav.bridge",
    permissions: ["bridge"],
  },
  {
    key: "workbench",
    labelKey: "nav.workbench",
    permissions: ["terminal", "browser"],
  },
  {
    key: "remote-desktop",
    labelKey: "nav.remoteDesktop",
    permissions: ["desktop", "mobile"],
  },
  {
    key: "admin-users",
    labelKey: "nav.adminUsers",
    permissions: ["users", "sso"],
  },
  {
    key: "models",
    labelKey: "nav.models",
    permissions: [
      "providers",
      "ollama_models",
      "onnx_models",
      "search",
      "voice",
    ],
  },
  {
    key: "admin-storage",
    labelKey: "nav.adminStorage",
    permissions: ["storage_backends"],
  },
  {
    key: "admin-plugins",
    labelKey: "nav.adminPlugins",
    permissions: ["plugins"],
  },
  {
    key: "admin-security",
    labelKey: "nav.security",
    permissions: ["security", "admin_console"],
  },
  {
    key: "admin-advanced",
    labelKey: "nav.adminAdvanced",
    permissions: [
      "envs",
      "observability",
      "backup",
      "tls",
      "captcha",
      "update",
    ],
  },
];

const DEFAULT_UNGROUPED = ["chat", "experts", "tasks", "token-usage"] as const;

const DEFAULT_GROUPS: readonly { id: string; items: readonly string[] }[] = [
  {
    id: "settings",
    items: [
      "personalization",
      "channels",
      "connectors",
      "skill-packages",
      "knowledge-bases",
      "bridge",
    ],
  },
  { id: "control", items: ["workbench", "remote-desktop"] },
  {
    id: "admin",
    items: [
      "admin-users",
      "models",
      "admin-storage",
      "admin-plugins",
      "admin-security",
      "admin-advanced",
    ],
  },
];

const NAV_BY_KEY = new Map(
  NAV_PERMISSION_CHIPS.map((item) => [item.key, item]),
);

export type PickerChip<T> =
  | { kind: "permission"; item: T }
  | { kind: "always"; key: string; label: string };

export interface PickerChipBlock<T> {
  kind: "chips";
  items: PickerChip<T>[];
}

export interface PickerPageBlock<T> {
  kind: "page";
  id: string;
  title: string;
  items: T[];
}

export type PickerBlock<T> = PickerChipBlock<T> | PickerPageBlock<T>;

export interface PickerGroup<T> {
  id: string;
  label: string;
  blocks: PickerBlock<T>[];
}

function groupLabel(
  id: string,
  name: string | null | undefined,
  translate: (key: string) => string,
): string {
  const custom = name?.trim() ?? "";
  if (custom) return custom;
  const labelKey = builtinNavGroupLabelKey(id);
  return labelKey ? translate(labelKey) : id;
}

/**
 * Permission picker sections following the operator's sidebar layout.
 * Hidden and omitted nav items stay in their default group so a personal
 * hide list cannot drop a permission from this form.
 */
export function buildPermissionPickerGroups<T extends { key: string }>(
  catalog: readonly T[],
  layout: SidebarNavLayout | null,
  translate: (key: string) => string,
): PickerGroup<T>[] {
  const byPerm = new Map<string, T>();
  for (const item of catalog) {
    if (!byPerm.has(item.key)) byPerm.set(item.key, item);
  }
  if (byPerm.size === 0) return [];

  const placed = new Map<string, string | null>();
  const explicitOrder: string[] = [];
  if (layout) {
    const groupIds = new Set(layout.groups.map((group) => group.id));
    for (const item of layout.items) {
      if (!NAV_BY_KEY.has(item.key) || item.hidden) continue;
      const groupId =
        item.group && groupIds.has(item.group) ? item.group : null;
      placed.set(item.key, groupId);
      explicitOrder.push(item.key);
    }
  }

  const ungrouped: string[] = [];
  const byGroup = new Map<string, string[]>();
  const push = (groupId: string | null, key: string) => {
    if (groupId === null) {
      ungrouped.push(key);
      return;
    }
    const list = byGroup.get(groupId) ?? [];
    list.push(key);
    byGroup.set(groupId, list);
  };
  for (const key of explicitOrder) push(placed.get(key) ?? null, key);
  for (const key of DEFAULT_UNGROUPED) {
    if (!placed.has(key)) push(null, key);
  }
  for (const group of DEFAULT_GROUPS) {
    for (const key of group.items) {
      if (!placed.has(key)) push(group.id, key);
    }
  }

  const blocksFor = (navKeys: readonly string[]): PickerBlock<T>[] => {
    const blocks: PickerBlock<T>[] = [];
    let chips: PickerChip<T>[] = [];
    const flush = () => {
      if (chips.length === 0) return;
      blocks.push({ kind: "chips", items: chips });
      chips = [];
    };
    for (const navKey of navKeys) {
      const nav = NAV_BY_KEY.get(navKey);
      if (!nav) continue;
      if (nav.permissions.length === 0) {
        chips.push({
          kind: "always",
          key: nav.key,
          label: translate(nav.labelKey),
        });
        continue;
      }
      const items = nav.permissions
        .map((key) => byPerm.get(key))
        .filter((item): item is T => Boolean(item));
      if (items.length === 0) continue;
      const only = items[0];
      if (nav.inline || (items.length === 1 && only)) {
        for (const item of items) {
          chips.push({ kind: "permission", item });
        }
        continue;
      }
      flush();
      blocks.push({
        kind: "page",
        id: nav.key,
        title: translate(nav.labelKey),
        items,
      });
    }
    flush();
    return blocks;
  };

  const groups: PickerGroup<T>[] = [];
  const ungroupedBlocks = blocksFor(ungrouped);
  if (ungroupedBlocks.length > 0) {
    groups.push({
      id: "ungrouped",
      label: translate("nav.ungrouped"),
      blocks: ungroupedBlocks,
    });
  }

  const seen = new Set<string>();
  const orderedGroupIds: { id: string; name?: string | null }[] = [];
  if (layout) {
    for (const group of layout.groups) {
      if (seen.has(group.id)) continue;
      seen.add(group.id);
      orderedGroupIds.push(group);
    }
  }
  for (const group of DEFAULT_GROUPS) {
    if (seen.has(group.id)) continue;
    orderedGroupIds.push({ id: group.id });
  }
  for (const group of orderedGroupIds) {
    const blocks = blocksFor(byGroup.get(group.id) ?? []);
    if (blocks.length === 0) continue;
    groups.push({
      id: group.id,
      label: groupLabel(group.id, group.name, translate),
      blocks,
    });
  }

  const covered = new Set(
    NAV_PERMISSION_CHIPS.flatMap((item) => item.permissions),
  );
  const orphans = catalog.filter(
    (item, index) =>
      !covered.has(item.key) &&
      catalog.findIndex((other) => other.key === item.key) === index,
  );
  if (orphans.length > 0) {
    groups.push({
      id: "other",
      label: translate("adminUsers.permGroupOther"),
      blocks: [
        {
          kind: "chips",
          items: orphans.map((item) => ({ kind: "permission" as const, item })),
        },
      ],
    });
  }
  return groups;
}
