/**
 * ProfileOverview.tsx — user profile overview.
 *
 * Single-column dossier with real stats from statsCounts, grouped profile
 * sections, optional review action, and no fabricated backend-unsupported data.
 */
import { useCallback, useEffect, useState } from "react";
import { Button, Skeleton, Space, Tag, Tooltip } from "antd";
import {
  ChevronRight,
  Crosshair,
  Loader2,
  MessageSquare,
  RefreshCw,
  Tags,
  User,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import {
  calendarDaysAgo,
  formatServerYmd,
} from "../../../utils/formatMessageTime";
import type { TFunction } from "i18next";

import {
  memoryDashboardApi,
  type AtomItem,
  type EntityItem,
  type StatsCounts,
} from "../../../api/modules/memoryDashboard";

import styles from "./Overview.module.less";

interface Props {
  agentId: string;
  /** Jump to the review tab when the profile-review action is clicked. */
  onReview?: () => void;
  /** Jump to the memory tree; entityId can auto-expand the corresponding topic. */
  onViewAll?: (entityId?: string) => void;
}

interface PageState {
  aboutMe: AtomItem[];
  focus: AtomItem[];
  toldMe: AtomItem[];
  entities: EntityItem[];
  counts: StatsCounts | null;
  firstLoading: boolean;
  refreshing: boolean;
}

const INITIAL_STATE: PageState = {
  aboutMe: [],
  focus: [],
  toldMe: [],
  entities: [],
  counts: null,
  firstLoading: true,
  refreshing: false,
};

/** Number of rows fetched per section. */
const SECTION_FETCH = 12;

/** Maximum visible rows per section before moving overflow behind view-all. */
const SECTION_VISIBLE = 6;

type TFn = TFunction;

interface ConceptItem {
  id: string;
  /** Owning entity_id used to auto-expand the topic when jumping to the memory library. */
  entityId: string;
  title: string;
  meta?: React.ReactNode;
}

export default function ProfileOverview({
  agentId,
  onReview,
  onViewAll,
}: Props) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [state, setState] = useState<PageState>(INITIAL_STATE);

  const loadAll = useCallback(async () => {
    if (!agentId) return;
    setState((s) => ({ ...s, refreshing: true }));

    const results = await Promise.allSettled([
      memoryDashboardApi.terminalAboutMe(agentId, SECTION_FETCH),
      memoryDashboardApi.terminalCurrentFocus(agentId, SECTION_FETCH),
      memoryDashboardApi.terminalThingsYouToldMe(agentId, SECTION_FETCH),
      memoryDashboardApi.terminalEntities(agentId, SECTION_FETCH),
      memoryDashboardApi.statsCounts(agentId),
    ]);

    const [aboutMe, focus, toldMe, entities, counts] = results;

    setState({
      aboutMe: aboutMe.status === "fulfilled" ? aboutMe.value.items : [],
      focus: focus.status === "fulfilled" ? focus.value.items : [],
      toldMe: toldMe.status === "fulfilled" ? toldMe.value.items : [],
      entities: entities.status === "fulfilled" ? entities.value.items : [],
      counts: counts.status === "fulfilled" ? counts.value : null,
      firstLoading: false,
      refreshing: false,
    });
  }, [agentId]);

  useEffect(() => {
    if (!agentId) return;
    void loadAll();
  }, [agentId, loadAll]);

  const { firstLoading, refreshing, counts } = state;
  const pending = counts?.candidates_pending ?? 0;

  return (
    <section className={styles.dossier}>
      {/* Dossier header: avatar, title, actions, and stats */}
      <header className={styles.dossierHeader}>
        <div className={styles.dossierTopRow}>
          <div className={styles.dossierAvatar} aria-hidden>
            <User size={16} />
          </div>
          <div className={styles.dossierHeadText}>
            <h2 className={styles.dossierTitle}>
              {t("memory.overview.heroTitle", "用户画像")}
            </h2>
            <div className={styles.dossierSubtitle}>
              {t(
                "memory.overview.profileSubtitle",
                "AI 当前对你的结构化理解，只展示高价值结论，并非完整记忆库。",
              )}
            </div>
          </div>
          <div className={styles.dossierActions}>
            {onReview && pending > 0 ? (
              <Button size="small" onClick={onReview}>
                {t("memory.overview.reviewAction", "整理画像")}
                <span className={styles.actionBadge}>{pending}</span>
              </Button>
            ) : null}
            <Tooltip title={t("common.refresh", "刷新")}>
              <Button
                size="small"
                icon={
                  refreshing ? <Loader2 size={14} /> : <RefreshCw size={14} />
                }
                onClick={() => void loadAll()}
                disabled={refreshing}
              />
            </Tooltip>
          </div>
        </div>

        <div className={styles.dossierStats}>
          {firstLoading ? (
            <Skeleton.Input
              active
              size="small"
              style={{ width: 300, height: 20, minHeight: 20 }}
            />
          ) : counts ? (
            <>
              <Stat
                value={counts.atoms}
                label={t("memory.overview.memories", "条记忆")}
              />
              <Stat
                value={counts.episodes}
                label={t("memory.overview.episodesShort", "段对话片段")}
              />
              <Stat
                value={counts.entities}
                label={t("memory.overview.entitiesShort", "个人物/事物")}
              />
              <Stat
                value={counts.atoms_delta_7d}
                label={t("memory.overview.atomsDelta7dShort", "条近7天新增")}
              />
            </>
          ) : null}
        </div>
      </header>

      {/* Body: one white card with vertical internal groups */}
      <div className={styles.dossierBody}>
        <ProfileGroup
          icon={<User size={14} />}
          title={t("memory.terminal.aboutMe", "关于你")}
          subtitle={t("memory.terminal.aboutMeDesc", "长期稳定的偏好与事实")}
          loading={firstLoading}
          items={state.aboutMe.map((a) => atomToConceptItem(a, t, timeZone))}
          emptyHint={t(
            "memory.terminal.emptyAboutMe",
            "Octop 还在了解你，多聊几次就会补上",
          )}
          onViewAll={onViewAll}
        />
        <ProfileGroup
          icon={<Crosshair size={14} />}
          title={t("memory.terminal.currentFocus", "当前重点")}
          subtitle={t(
            "memory.terminal.currentFocusDesc",
            "进行中的任务和最近的决定",
          )}
          loading={firstLoading}
          items={state.focus.map((a) => atomToConceptItem(a, t, timeZone))}
          emptyHint={t("memory.terminal.emptyFocus", "暂时没有进行中的任务")}
          onViewAll={onViewAll}
        />
        <ProfileGroup
          icon={<MessageSquare size={14} />}
          title={t("memory.terminal.toldMe", "你提到的事实")}
          subtitle={t(
            "memory.terminal.toldMeDesc",
            "最近被 Octop 记下的关键内容",
          )}
          loading={firstLoading}
          items={state.toldMe.map((a) => atomToConceptItem(a, t, timeZone))}
          emptyHint={t("memory.terminal.emptyToldMe", "还没有记下明确事实")}
          onViewAll={onViewAll}
        />
        <EntityGroup loading={firstLoading} entities={state.entities} t={t} />
      </div>
    </section>
  );
}

function Stat({
  value,
  label,
  warn,
}: {
  value: React.ReactNode;
  label: string;
  warn?: boolean;
}) {
  return (
    <div className={styles.statItem}>
      <span
        className={`${styles.statValue} ${warn ? styles.statValueWarn : ""}`}
      >
        {value}
      </span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

function atomToConceptItem(a: AtomItem, t: TFn, timeZone: string): ConceptItem {
  const time = relTime(a.occurred_at, t, timeZone);
  return {
    id: a.id,
    entityId: a.entity_id,
    title: a.assertion,
    meta: (
      <Space size={6}>
        {a.kind ? (
          <Tag color={kindColor(a.kind)} style={{ marginRight: 0 }}>
            {kindLabel(a.kind, t)}
          </Tag>
        ) : null}
        <span className={styles.metaSub}>
          {confidenceLabel(a.confidence, t)}
          {time ? ` · ${time}` : ""}
        </span>
        <ImportanceStars importance={a.importance} t={t} />
      </Space>
    ),
  };
}

/**
 * One profile group: icon, title, subtitle, and a list of rows.
 * Shows at most SECTION_VISIBLE rows, then routes overflow to the memory tree.
 */
function ProfileGroup({
  icon,
  title,
  subtitle,
  loading,
  items,
  emptyHint,
  onViewAll,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  loading: boolean;
  items: ConceptItem[];
  emptyHint: string;
  onViewAll?: (entityId?: string) => void;
}) {
  const { t } = useTranslation();
  const visible = items.slice(0, SECTION_VISIBLE);
  const hasMore = items.length > SECTION_VISIBLE;
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  let body: React.ReactNode;
  if (loading) {
    body = (
      <div className={styles.groupSkeleton}>
        <Skeleton paragraph={{ rows: 2 }} active title={false} />
      </div>
    );
  } else if (items.length === 0) {
    body = <div className={styles.groupEmpty}>{emptyHint}</div>;
  } else {
    body = (
      <>
        <div className={styles.groupList}>
          {visible.map((it) => (
            <Tooltip
              key={it.id}
              title={
                onViewAll
                  ? t(
                      "memory.overview.rowHintToLibrary",
                      "如有误，可在记忆库中弃用",
                    )
                  : undefined
              }
              placement="top"
              mouseEnterDelay={0.4}
            >
              {onViewAll ? (
                <button
                  type="button"
                  className={`${styles.groupRow} ${styles.groupRowClickable}`}
                  onMouseEnter={() => setHoveredId(it.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => onViewAll(it.entityId)}
                >
                  <span className={styles.groupRowText}>{it.title}</span>
                  <span className={styles.groupRowMeta}>
                    {it.meta}
                    <span
                      className={`${styles.rowGoLibraryLabel} ${
                        hoveredId === it.id
                          ? styles.rowGoLibraryLabelVisible
                          : ""
                      }`}
                    >
                      {t("memory.overview.rowGoLibrary", "去记忆库 →")}
                    </span>
                  </span>
                </button>
              ) : (
                <div className={styles.groupRow}>
                  <span className={styles.groupRowText}>{it.title}</span>
                  <span className={styles.groupRowMeta}>{it.meta}</span>
                </div>
              )}
            </Tooltip>
          ))}
        </div>
        {hasMore && onViewAll ? (
          <button
            type="button"
            className={styles.groupMore}
            onClick={() => onViewAll()}
          >
            {t("memory.overview.viewAll", "查看全部")}
            <ChevronRight className={styles.groupMoreIcon} size={14} />
          </button>
        ) : null}
      </>
    );
  }

  return (
    <div className={styles.group}>
      <div className={styles.groupHead}>
        <span className={styles.groupIcon} aria-hidden>
          {icon}
        </span>
        <span className={styles.groupTitle}>{title}</span>
        <span className={styles.groupSubtitle}>{subtitle}</span>
      </div>
      {body}
    </div>
  );
}

/** Key people/things rendered as a bottom chip row. */
function EntityGroup({
  loading,
  entities,
  t,
}: {
  loading: boolean;
  entities: EntityItem[];
  t: TFn;
}) {
  return (
    <div className={styles.group}>
      <div className={styles.groupHead}>
        <span className={styles.groupIcon} aria-hidden>
          <Tags size={16} />
        </span>
        <span className={styles.groupTitle}>
          {t("memory.terminal.entities", "关键人事物")}
        </span>
        <span className={styles.groupSubtitle}>
          {t("memory.terminal.entitiesDesc", "记忆中出现最频繁的主题")}
        </span>
      </div>
      {loading ? (
        <div className={styles.groupSkeleton}>
          <Skeleton paragraph={{ rows: 1 }} active title={false} />
        </div>
      ) : entities.length === 0 ? (
        <div className={styles.groupEmpty}>
          {t("memory.terminal.emptyEntities", "暂时还没有高频人事物")}
        </div>
      ) : (
        <div className={styles.chipWrap}>
          {entities.map((e) => (
            <span
              key={e.id}
              className={styles.chip}
              title={entityTypeLabel(e.entity_type, t)}
            >
              <span className={styles.chipName}>{e.canonical_name}</span>
              <span className={styles.chipCount}>{e.atom_count}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function kindColor(k: string): string {
  switch (k) {
    case "Fact":
      return "default";
    case "Decision":
      return "geekblue";
    case "Task":
      return "orange";
    case "Preference":
      return "green";
    case "ConflictCandidate":
      return "red";
    default:
      return "default";
  }
}

function kindLabel(k: string, t: TFn): string {
  switch (k) {
    case "Fact":
      return t("memory.kind.fact", "事实");
    case "Decision":
      return t("memory.kind.decision", "决定");
    case "Task":
      return t("memory.kind.task", "任务");
    case "Preference":
      return t("memory.kind.preference", "偏好");
    case "ConflictCandidate":
      return t("memory.kind.conflict", "可能矛盾");
    default:
      return k;
  }
}

function confidenceLabel(c: string, t: TFn): string {
  switch (c) {
    case "high":
      return t("memory.confidence.high", "高置信");
    case "medium":
      return t("memory.confidence.medium", "中置信");
    default:
      return t("memory.confidence.low", "低置信");
  }
}

/** Format occurred_at as today, yesterday, N days ago, or yyyy-MM-dd; returns null when absent. */
function relTime(
  s: string | null | undefined,
  t: TFn,
  timeZone: string,
): string | null {
  if (!s) return null;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return null;
  const diff = calendarDaysAgo(d, timeZone);
  if (Number.isNaN(diff)) return null;
  if (diff <= 0) return t("memory.time.today", "今天");
  if (diff === 1) return t("memory.time.yesterday", "昨天");
  if (diff < 7)
    return t("memory.time.daysAgo", "{{n}} 天前").replace(
      "{{n}}",
      String(diff),
    );
  return formatServerYmd(d, timeZone);
}

function entityTypeLabel(raw: string, t: TFn): string {
  switch ((raw || "").toLowerCase()) {
    case "person":
      return t("memory.entityType.person", "人物");
    case "place":
      return t("memory.entityType.place", "地点");
    case "project":
      return t("memory.entityType.project", "项目");
    case "tool":
      return t("memory.entityType.tool", "工具");
    case "concept":
      return t("memory.entityType.concept", "概念");
    case "organization":
      return t("memory.entityType.organization", "组织");
    case "event":
      return t("memory.entityType.event", "事件");
    default:
      return raw || t("memory.entityType.other", "其它");
  }
}

function ImportanceStars({ importance, t }: { importance: string; t: TFn }) {
  const n = importance === "high" ? 3 : importance === "medium" ? 2 : 1;
  const label =
    importance === "high"
      ? t("memory.importance.high", "非常重要")
      : importance === "medium"
      ? t("memory.importance.medium", "重要")
      : t("memory.importance.low", "一般");
  return (
    <span
      title={`${t("memory.importance.title", "重要程度")}：${label}`}
      style={{ color: "#faad14", fontSize: 13, letterSpacing: 1 }}
    >
      {"★".repeat(n)}
      <span style={{ color: "#d9d9d9" }}>{"★".repeat(3 - n)}</span>
    </span>
  );
}
