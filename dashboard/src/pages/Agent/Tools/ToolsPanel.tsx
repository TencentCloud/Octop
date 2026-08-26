import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import { Empty, Spin, Switch, Tooltip } from "antd";
import type { LucideIcon } from "lucide-react";
import {
  AppWindow,
  BookOpen,
  Brain,
  CalendarClock,
  Clock,
  Code2,
  Eye,
  FileKey,
  FilePen,
  FileSearch,
  FileText,
  Folder,
  Globe,
  Handshake,
  Image,
  Library,
  ListChecks,
  ListTodo,
  MessageCircle,
  Monitor,
  MousePointerClick,
  Move,
  Pencil,
  Play,
  Plug,
  Plus,
  Puzzle,
  Search,
  Send,
  Smartphone,
  SquareTerminal,
  Trash2,
  Users,
  Video,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  agentToolsApi,
  type ToolSettingsItem,
} from "../../../api/modules/agentTools";
import styles from "./ToolsPanel.module.less";

const CATEGORY_ORDER = [
  "filesystem",
  "orchestration",
  "web",
  "media",
  "memory",
  "cron",
  "knowledge",
  "mobile",
  "teams",
  "misc",
  "plugin",
] as const;

/** Icon square fill per category. */
const CATEGORY_ACCENT: Record<string, string> = {
  filesystem: "#3B82F6",
  orchestration: "#8B5CF6",
  web: "#22C55E",
  media: "#EC4899",
  memory: "#F59E0B",
  cron: "#6366F1",
  knowledge: "#10B981",
  mobile: "#0EA5E9",
  teams: "#F97316",
  misc: "#64748B",
  plugin: "#A855F7",
};

const TOOL_ICONS: Record<string, LucideIcon> = {
  ls: Folder,
  read_file: FileSearch,
  write_file: FilePen,
  edit_file: Pencil,
  glob: Search,
  grep: FileText,
  execute: SquareTerminal,
  write_todos: ListTodo,
  task: Users,
  current_time: Clock,
  web_fetch: Globe,
  browser_use: AppWindow,
  desktop_screenshot: Monitor,
  send_file_to_user: Send,
  read_env_file: FileKey,
  write_env_file: FileKey,
  tavily_search: Search,
  brave_search: Search,
  google_search: Search,
  kimi_search: Search,
  searchfree_search: Search,
  generate_image: Image,
  generate_video: Video,
  memory_search: Brain,
  memory_get: BookOpen,
  acp_runner: Plug,
  cronjob_list: ListChecks,
  cronjob_get: Eye,
  cronjob_create: Plus,
  cronjob_update: CalendarClock,
  cronjob_delete: Trash2,
  cronjob_run_now: Play,
  search_knowledge: Library,
  mobile_screenshot: Smartphone,
  mobile_tap: MousePointerClick,
  mobile_swipe: Move,
  mobile_launch_app: AppWindow,
  mobile_ui_dump: Code2,
  mobile_handoff_to_user: Handshake,
  agent_list: Users,
  ask_agent: MessageCircle,
};

function toolKey(tool: ToolSettingsItem): string {
  return tool.source === "plugin"
    ? `plugin:${tool.plugin_id ?? ""}:${tool.name}`
    : `builtin:${tool.name}`;
}

function toolIcon(tool: ToolSettingsItem): LucideIcon {
  return TOOL_ICONS[tool.name] ?? (tool.source === "plugin" ? Puzzle : Wrench);
}

interface ToolsPanelProps {
  agentId: string | null;
}

/**
 * Full tools surface (builtin + plugin), shared by Personalization tab and
 * Experts ToolCatalogDrawer — mirrors SkillsTabs.
 */
export default function ToolsPanel({ agentId }: ToolsPanelProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [tools, setTools] = useState<ToolSettingsItem[]>([]);
  const [enabledMap, setEnabledMap] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!agentId) {
      setTools([]);
      setEnabledMap({});
      return;
    }
    setLoading(true);
    try {
      const res = await agentToolsApi.get(agentId);
      setTools(res.tools);
      const next: Record<string, boolean> = {};
      for (const tool of res.tools) {
        next[toolKey(tool)] = tool.enabled;
      }
      setEnabledMap(next);
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("toolSettings.loadFailed"),
      );
      setTools([]);
      setEnabledMap({});
    } finally {
      setLoading(false);
    }
  }, [agentId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => {
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
      category,
      tools: byCategory.get(category) ?? [],
    }));
  }, [tools]);

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
      const next: Record<string, boolean> = {};
      for (const row of res.tools) {
        next[
          row.source === "plugin"
            ? `plugin:${row.plugin_id ?? ""}:${row.name}`
            : `builtin:${row.name}`
        ] = row.enabled;
      }
      setTools(res.tools);
      setEnabledMap(next);
    } catch (err) {
      setEnabledMap((cur) => ({ ...cur, [key]: prev }));
      message.error(
        err instanceof Error ? err.message : t("toolSettings.saveFailed"),
      );
    } finally {
      setSavingKey(null);
    }
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
    return <Empty description={t("toolSettings.empty")} />;
  }

  return (
    <div className={styles.panel}>
      <p className={styles.hint}>{t("toolSettings.hint")}</p>
      <div className={styles.groups}>
        {groups.map((group) => (
          <section key={group.category} className={styles.group}>
            <h3 className={styles.groupTitle}>
              {t(`toolSettings.categories.${group.category}`, {
                defaultValue: group.category,
              })}
            </h3>
            <div className={styles.grid}>
              {group.tools.map((tool) => {
                const key = toolKey(tool);
                const checked = enabledMap[key] ?? tool.enabled;
                const accent =
                  CATEGORY_ACCENT[tool.category] ?? CATEGORY_ACCENT.misc;
                const Icon = toolIcon(tool);
                const switchEl = (
                  <Switch
                    size="small"
                    checked={checked && tool.available !== false}
                    disabled={
                      !tool.disableable ||
                      tool.available === false ||
                      savingKey === key
                    }
                    loading={savingKey === key}
                    onChange={(value) => void handleToggle(tool, value)}
                    onClick={(_, e) => e.stopPropagation()}
                  />
                );
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
                      {tool.source === "plugin" && tool.description ? (
                        <div className={styles.desc} title={tool.description}>
                          {tool.description}
                        </div>
                      ) : (
                        <div className={styles.name} title={tool.name}>
                          {tool.name}
                        </div>
                      )}
                    </div>
                    <div className={styles.cardAction}>
                      {tool.disableable ? (
                        switchEl
                      ) : (
                        <Tooltip title={t("toolSettings.criticalHint")}>
                          <span>{switchEl}</span>
                        </Tooltip>
                      )}
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
