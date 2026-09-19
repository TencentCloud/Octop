import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import { Empty, Segmented, Spin, Switch, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  agentToolsApi,
  type ToolSettingsItem,
} from "../../../api/modules/agentTools";
import { pluginsApi, type AgentPlugin } from "../../../api/modules/plugins";
import { builtinToolIcon } from "../../../utils/builtinToolIcons";
import { PluginIconView } from "../../Admin/Plugins/PluginIconView";
import { PluginGroupTag } from "../../Admin/Plugins/PluginGroupTag";
import {
  PLUGIN_GROUP_ORDER,
  isKnownPluginGroup,
} from "../../Admin/Plugins/pluginGroups";
import pluginStyles from "../../Admin/Plugins/index.module.less";
import styles from "./ToolsPanel.module.less";

const GROUP_ALL = "all";

const CATEGORY_ORDER = [
  "filesystem",
  "orchestration",
  "interaction",
  "web",
  "media",
  "memory",
  "cron",
  "knowledge",
  "mobile",
  "teams",
  "misc",
] as const;

/** Icon square fill per category. */
const CATEGORY_ACCENT: Record<string, string> = {
  filesystem: "#3B82F6",
  orchestration: "#8B5CF6",
  interaction: "#14B8A6",
  web: "#22C55E",
  media: "#EC4899",
  memory: "#F59E0B",
  cron: "#6366F1",
  knowledge: "#10B981",
  mobile: "#0EA5E9",
  teams: "#F97316",
  misc: "#64748B",
};

type PluginMeta = {
  name: string;
  icon: string | null;
  group: string | null;
  description: string | null;
};

function toolKey(tool: ToolSettingsItem): string {
  return tool.source === "plugin"
    ? `plugin:${tool.plugin_id ?? ""}:${tool.name}`
    : `builtin:${tool.name}`;
}

/** Prefer API label, else a short phrase from description (not snake_case id). */
function pluginToolTitle(tool: ToolSettingsItem): string {
  if (tool.label && tool.label !== tool.name) return tool.label;
  // Label may already be the CJK registration name.
  if (tool.label && !/^[a-zA-Z0-9_-]+$/.test(tool.label)) return tool.label;
  const desc = tool.description?.trim();
  if (desc) {
    const stripped = desc.replace(/^\[原名:\s*.+?\]\s*/, "");
    const phrase = stripped.split(/[，,。！？.!?\n]/)[0]?.trim();
    if (phrase && phrase.length >= 2 && phrase.length <= 36) return phrase;
  }
  return tool.label || tool.name;
}

interface ToolsPanelProps {
  agentId: string | null;
  /** Which tool source to show. Defaults to built-in. */
  source?: "builtin" | "plugin";
}

/**
 * Tools enable/disable surface shared by Personalization and Experts.
 */
export default function ToolsPanel({
  agentId,
  source = "builtin",
}: ToolsPanelProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [tools, setTools] = useState<ToolSettingsItem[]>([]);
  const [enabledMap, setEnabledMap] = useState<Record<string, boolean>>({});
  const [pluginMeta, setPluginMeta] = useState<Record<string, PluginMeta>>({});
  const [activeGroup, setActiveGroup] = useState<string>(GROUP_ALL);

  const applyTools = useCallback(
    (all: ToolSettingsItem[]) => {
      const filtered = all.filter((tool) => tool.source === source);
      setTools(filtered);
      const next: Record<string, boolean> = {};
      for (const tool of filtered) {
        next[toolKey(tool)] = tool.enabled;
      }
      setEnabledMap(next);
    },
    [source],
  );

  const applyPluginMeta = useCallback((plugins: AgentPlugin[]) => {
    const next: Record<string, PluginMeta> = {};
    for (const plugin of plugins) {
      next[plugin.id] = {
        name: (plugin.name || plugin.id).trim() || plugin.id,
        icon: plugin.icon?.trim() || null,
        group: plugin.group?.trim() || null,
        description: plugin.description?.trim() || null,
      };
    }
    setPluginMeta(next);
  }, []);

  const load = useCallback(async () => {
    if (!agentId) {
      setTools([]);
      setEnabledMap({});
      setPluginMeta({});
      return;
    }
    setLoading(true);
    try {
      if (source === "plugin") {
        const [toolsRes, pluginsRes] = await Promise.all([
          agentToolsApi.get(agentId),
          pluginsApi.listAgentPlugins(agentId),
        ]);
        applyTools(toolsRes.tools);
        applyPluginMeta(pluginsRes.plugins);
      } else {
        const res = await agentToolsApi.get(agentId);
        applyTools(res.tools);
        setPluginMeta({});
      }
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("toolSettings.loadFailed"),
      );
      setTools([]);
      setEnabledMap({});
      setPluginMeta({});
    } finally {
      setLoading(false);
    }
  }, [agentId, applyPluginMeta, applyTools, source, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const builtinGroups = useMemo(() => {
    if (source !== "builtin") return [];
    const byCategory = new Map<string, ToolSettingsItem[]>();
    for (const tool of tools) {
      const list = byCategory.get(tool.category) ?? [];
      list.push(tool);
      byCategory.set(tool.category, list);
    }
    const ordered = CATEGORY_ORDER.filter((c) => byCategory.has(c));
    const extras = [...byCategory.keys()]
      .filter(
        (c) => !CATEGORY_ORDER.includes(c as (typeof CATEGORY_ORDER)[number]),
      )
      .sort();
    return [...ordered, ...extras].map((category) => ({
      key: category,
      title: t(`toolSettings.categories.${category}`, {
        defaultValue: category,
      }),
      tools: byCategory.get(category) ?? [],
    }));
  }, [source, tools, t]);

  const pluginGroups = useMemo(() => {
    if (source !== "plugin") return [];
    const byPlugin = new Map<
      string,
      {
        id: string;
        name: string;
        icon: string | null;
        group: string | null;
        description: string | null;
        tools: ToolSettingsItem[];
      }
    >();
    for (const tool of tools) {
      const id = tool.plugin_id?.trim() || "unknown";
      const meta = pluginMeta[id];
      const name = meta?.name || tool.plugin_name?.trim() || id;
      const icon = meta?.icon ?? tool.plugin_icon?.trim() ?? null;
      const group = meta?.group ?? null;
      const description = meta?.description ?? null;
      const existing = byPlugin.get(id);
      if (existing) {
        existing.tools.push(tool);
        if (!existing.icon && icon) existing.icon = icon;
        if (!existing.group && group) existing.group = group;
        if (existing.name === id && name !== id) existing.name = name;
        if (!existing.description && description) {
          existing.description = description;
        }
      } else {
        byPlugin.set(id, {
          id,
          name,
          icon,
          group,
          description,
          tools: [tool],
        });
      }
    }
    return [...byPlugin.values()].sort((a, b) => {
      const ai = PLUGIN_GROUP_ORDER.indexOf(
        a.group as (typeof PLUGIN_GROUP_ORDER)[number],
      );
      const bi = PLUGIN_GROUP_ORDER.indexOf(
        b.group as (typeof PLUGIN_GROUP_ORDER)[number],
      );
      const ag = ai >= 0 ? ai : PLUGIN_GROUP_ORDER.length;
      const bg = bi >= 0 ? bi : PLUGIN_GROUP_ORDER.length;
      if (ag !== bg) return ag - bg;
      return a.name.localeCompare(b.name, "zh");
    });
  }, [pluginMeta, source, tools]);

  const handleToggle = async (tool: ToolSettingsItem, enabled: boolean) => {
    if (!agentId || !tool.disableable) return;
    // Globally disabled plugins stay unavailable — don't persist a false "on".
    if (tool.available === false && enabled) return;
    const key = toolKey(tool);
    const prev = enabledMap[key] ?? tool.enabled;
    setEnabledMap((cur) => ({ ...cur, [key]: enabled }));
    setSavingKey(key);
    try {
      const res = await agentToolsApi.patch(agentId, tool.name, {
        enabled,
        source: tool.source,
        plugin_id: tool.plugin_id ?? undefined,
      });
      applyTools(res.tools);
    } catch (err) {
      setEnabledMap((cur) => ({ ...cur, [key]: prev }));
      message.error(
        err instanceof Error ? err.message : t("toolSettings.saveFailed"),
      );
    } finally {
      setSavingKey(null);
    }
  };

  const renderSwitch = (tool: ToolSettingsItem) => {
    const key = toolKey(tool);
    const checked = enabledMap[key] ?? tool.enabled;
    const switchEl = (
      <Switch
        size="small"
        checked={checked && tool.available !== false}
        disabled={
          !tool.disableable || tool.available === false || savingKey === key
        }
        loading={savingKey === key}
        onChange={(value) => void handleToggle(tool, value)}
        onClick={(_, e) => e.stopPropagation()}
      />
    );
    if (!tool.disableable) {
      return (
        <Tooltip title={t("toolSettings.criticalHint")}>
          <span>{switchEl}</span>
        </Tooltip>
      );
    }
    return switchEl;
  };

  if (!agentId) {
    return (
      <Empty
        description={t("skills.noAgentSelected")}
        style={{ marginTop: 64 }}
      />
    );
  }

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spin />
      </div>
    );
  }

  if (tools.length === 0) {
    return (
      <Empty
        description={
          source === "plugin"
            ? t("toolSettings.emptyPlugin")
            : t("toolSettings.empty")
        }
      />
    );
  }

  if (source === "plugin") {
    const groupOptions = (() => {
      const present = new Set<string>();
      for (const row of pluginGroups) {
        const g = (row.group || "").trim().toLowerCase();
        if (g) present.add(g);
      }
      const ordered = PLUGIN_GROUP_ORDER.filter((g) => present.has(g));
      const extras = [...present]
        .filter((g) => !isKnownPluginGroup(g))
        .sort((a, b) => a.localeCompare(b));
      return [
        { value: GROUP_ALL, label: t("plugins.groupAll") },
        ...ordered.map((g) => ({
          value: g,
          label: t(`plugins.groups.${g}`),
        })),
        ...extras.map((g) => ({
          value: g,
          label: t("plugins.groupUnknown"),
        })),
      ];
    })();
    const filteredGroups =
      activeGroup === GROUP_ALL
        ? pluginGroups
        : pluginGroups.filter(
            (row) => (row.group || "").trim().toLowerCase() === activeGroup,
          );

    return (
      <div className={styles.panel}>
        <p className={styles.hint}>{t("toolSettings.hintPlugin")}</p>
        {groupOptions.length > 1 ? (
          <div className={pluginStyles.groupTabsWrap}>
            <Segmented
              block
              size="large"
              value={activeGroup}
              onChange={(v) => setActiveGroup(String(v))}
              options={groupOptions}
              className={pluginStyles.groupTabs}
            />
          </div>
        ) : null}
        {filteredGroups.length === 0 ? (
          <Empty description={t("plugins.emptyGroup")} />
        ) : (
          <div className={pluginStyles.cardGrid}>
            {filteredGroups.map((group) => {
              const anyUnavailable = group.tools.some(
                (tool) => tool.available === false,
              );
              return (
                <article
                  key={group.id}
                  className={`${pluginStyles.card}${
                    anyUnavailable ? ` ${pluginStyles.cardDisabled}` : ""
                  }`}
                >
                  <div className={pluginStyles.cardBody}>
                    <div className={pluginStyles.cardTop}>
                      <PluginIconView
                        icon={group.icon}
                        size={32}
                        className={pluginStyles.cardIcon}
                      />
                      <div className={pluginStyles.cardTitleCol}>
                        <h3 className={pluginStyles.cardName}>{group.name}</h3>
                        <div className={pluginStyles.cardChips}>
                          <PluginGroupTag group={group.group} />
                          <div className={styles.pluginIdChip} title={group.id}>
                            {group.id}
                          </div>
                        </div>
                      </div>
                    </div>
                    <p className={pluginStyles.cardDesc}>
                      {group.description ||
                        t("toolSettings.pluginToolCount", {
                          count: group.tools.length,
                        })}
                    </p>
                    <div className={styles.pluginToolList}>
                      {group.tools.map((tool) => {
                        const key = toolKey(tool);
                        const title = pluginToolTitle(tool);
                        const showDesc =
                          !!tool.description &&
                          tool.description !== title &&
                          !tool.description.startsWith(`[原名: ${title}]`);
                        return (
                          <div
                            key={key}
                            className={`${pluginStyles.detailToolItem}${
                              tool.available === false
                                ? ` ${pluginStyles.detailToolItemOff}`
                                : ""
                            }`}
                          >
                            <div className={pluginStyles.detailToolMeta}>
                              <div className={pluginStyles.detailToolNameRow}>
                                <span
                                  className={styles.pluginToolTitle}
                                  title={title}
                                >
                                  {title}
                                </span>
                                {tool.available === false ? (
                                  <Tooltip
                                    title={t("toolSettings.unavailableHint")}
                                  >
                                    <span className={styles.unavailableBadge}>
                                      {t("toolSettings.unavailable")}
                                    </span>
                                  </Tooltip>
                                ) : null}
                              </div>
                              {showDesc ? (
                                <div
                                  className={pluginStyles.detailToolDesc}
                                  title={tool.description ?? undefined}
                                >
                                  {tool.description?.replace(
                                    /^\[原名:\s*.+?\]\s*/,
                                    "",
                                  )}
                                </div>
                              ) : null}
                            </div>
                            <div className={pluginStyles.detailToolActions}>
                              {renderSwitch(tool)}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <p className={styles.hint}>{t("toolSettings.hint")}</p>
      <div className={styles.groups}>
        {builtinGroups.map((group) => (
          <section key={group.key} className={styles.group}>
            <h3 className={styles.groupTitle}>{group.title}</h3>
            <div className={styles.grid}>
              {group.tools.map((tool) => {
                const key = toolKey(tool);
                const accent =
                  CATEGORY_ACCENT[tool.category] ?? CATEGORY_ACCENT.misc;
                const Icon = builtinToolIcon(tool.name);
                return (
                  <div
                    key={key}
                    className={`${styles.card}${
                      tool.available === false
                        ? ` ${styles.cardUnavailable}`
                        : ""
                    }`}
                    style={
                      {
                        "--tool-accent": accent,
                      } as CSSProperties
                    }
                  >
                    <div className={styles.icon} aria-hidden>
                      <Icon size={18} strokeWidth={2.2} />
                    </div>
                    <div className={styles.cardBody}>
                      <div className={styles.labelRow}>
                        <div className={styles.label} title={tool.label}>
                          {tool.label}
                        </div>
                        {tool.available === false ? (
                          <Tooltip title={t("toolSettings.unavailableHint")}>
                            <span className={styles.unavailableBadge}>
                              {t("toolSettings.unavailable")}
                            </span>
                          </Tooltip>
                        ) : null}
                      </div>
                      <div className={styles.name} title={tool.name}>
                        {tool.name}
                      </div>
                    </div>
                    <div className={styles.cardAction}>
                      {renderSwitch(tool)}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
