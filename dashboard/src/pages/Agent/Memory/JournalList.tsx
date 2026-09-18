/**
 * JournalList.tsx — story-style activity timeline.
 *
 * User-facing Agent activity timeline, not an audit log. Pipeline actions such
 * as capture/extract/page_regen are grouped into story cards by time window,
 * while key events such as promote/reject/deprecate remain standalone.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Empty, Pagination, Select, Skeleton, Space, Tag } from "antd";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  memoryDashboardApi,
  type ExtractRunStats,
  type JournalItem,
  type ListJournalBody,
} from "../../../api/modules/memoryDashboard";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import {
  calendarDaysAgo,
  formatServerHourMinute,
  formatServerYmd,
} from "../../../utils/formatMessageTime";

const PAGE_SIZE = 30;

const actionOptions = (t: TFunction) => [
  { value: "", label: t("memory.journal.filter.all") },
  { value: "extract_run", label: t("memory.journal.action.extractRun") },
  { value: "promote", label: t("memory.journal.action.promote") },
  { value: "reject", label: t("memory.journal.action.reject") },
  { value: "deprecate", label: t("memory.journal.action.deprecate") },
  { value: "create", label: t("memory.journal.action.create") },
  { value: "user_edit", label: t("memory.journal.filter.userEdit") },
  { value: "page_regen", label: t("memory.journal.filter.pageRegen") },
];

const ACTION_COLOR: Record<string, string> = {
  extract_run: "cyan",
  capture: "default",
  extract: "blue",
  promote: "purple",
  reject: "red",
  deprecate: "volcano",
  page_regen: "geekblue",
  create: "green",
  update: "blue",
  user_edit: "blue",
  merge: "gold",
};

const ACTION_HEX: Record<string, string> = {
  extract_run: "#13c2c2",
  capture: "#8c8c8c",
  extract: "#1677ff",
  promote: "#722ed1",
  reject: "#ff4d4f",
  deprecate: "#fa541c",
  page_regen: "#2f54eb",
  create: "#52c41a",
  update: "#1677ff",
  user_edit: "#1677ff",
  merge: "#faad14",
};

/** Internal pipeline actions that should be aggregated into one story. */
const PIPELINE_ACTIONS = new Set(["capture", "extract", "page_regen"]);
/** Maximum time gap within one aggregate group. */
const GROUP_GAP_MS = 60_000;

interface Props {
  agentId: string;
}

export default function JournalList({ agentId }: Props) {
  const timeZone = useServerTimezone();
  const { t } = useTranslation();
  const [items, setItems] = useState<JournalItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    const body: ListJournalBody = {
      offset: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    };
    if (action) body.action = action;
    try {
      const r = await memoryDashboardApi.listJournal(agentId, body);
      setItems(r.items);
      setTotal(r.total);
    } finally {
      setLoading(false);
    }
  }, [agentId, page, action]);

  useEffect(() => {
    if (!agentId) return;
    void load();
  }, [agentId, load]);

  // ``t`` is intentionally excluded from the deps — a fresh ``t`` ref per
  // render would rebuild buckets (and re-render the tree) on every keystroke.
  const days = useMemo(
    () => buildDays(items, timeZone, t),
    [items, timeZone], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <Card size="small">
      <Space style={{ marginBottom: 16 }} wrap>
        <span style={{ color: "#595959" }}>
          {t("memory.journal.filter.label")}
        </span>
        <Select
          style={{ width: 180 }}
          value={action}
          onChange={(v) => {
            setAction(v);
            setPage(1);
          }}
          options={actionOptions(t)}
        />
      </Space>

      {loading && items.length === 0 ? (
        <Skeleton active />
      ) : items.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("memory.journal.empty")}
        />
      ) : (
        <div>
          {days.map((day) => (
            <DaySection
              key={day.label}
              day={day}
              timeZone={timeZone}
              expanded={expanded}
              onToggle={(key) => setExpanded((s) => ({ ...s, [key]: !s[key] }))}
            />
          ))}
        </div>
      )}

      <div style={{ marginTop: 16, textAlign: "right" }}>
        <Pagination
          current={page}
          pageSize={PAGE_SIZE}
          total={total}
          showSizeChanger={false}
          onChange={setPage}
        />
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Child component: one section per day.
// ---------------------------------------------------------------------------

interface DayBucket {
  label: string;
  groups: Group[];
}

interface Group {
  /** Stable key for expansion state. */
  key: string;
  /** Representative timestamp shown on the left. */
  timestamp: string;
  /** Internal details, one item for a single event. */
  items: JournalItem[];
  /** Whether this is an aggregated pipeline story. */
  isPipelineGroup: boolean;
}

function DaySection({
  day,
  timeZone,
  expanded,
  onToggle,
}: {
  day: DayBucket;
  timeZone: string;
  expanded: Record<string, boolean>;
  onToggle: (key: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div style={{ marginBottom: 20 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "#8c8c8c",
          margin: "4px 0 12px",
          letterSpacing: 0.3,
        }}
      >
        {day.label}
        <span style={{ marginLeft: 8, fontWeight: 400 }}>
          · {t("memory.journal.itemsCount", { n: day.groups.length })}
        </span>
      </div>
      <div style={{ position: "relative", paddingLeft: 16 }}>
        {/* Timeline vertical line */}
        <div
          style={{
            position: "absolute",
            left: 5,
            top: 4,
            bottom: 4,
            width: 1,
            background: "#f0f0f0",
          }}
        />
        {day.groups.map((g) => (
          <GroupRow
            key={g.key}
            group={g}
            timeZone={timeZone}
            isExpanded={!!expanded[g.key]}
            onToggle={() => onToggle(g.key)}
          />
        ))}
      </div>
    </div>
  );
}

function GroupRow({
  group,
  timeZone,
  isExpanded,
  onToggle,
}: {
  group: Group;
  timeZone: string;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  if (group.isPipelineGroup) {
    return (
      <PipelineStoryRow
        group={group}
        timeZone={timeZone}
        isExpanded={isExpanded}
        onToggle={onToggle}
      />
    );
  }
  // Single standalone event.
  return <SingleEventRow item={group.items[0]} timeZone={timeZone} />;
}

/** Pipeline story card: capture/extract/page_regen aggregation. */
function PipelineStoryRow({
  group,
  timeZone,
  isExpanded,
  onToggle,
}: {
  group: Group;
  timeZone: string;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const summary = pipelineSummary(group.items, t);
  const dotColor = ACTION_HEX["capture"];
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 12,
          cursor: "pointer",
          padding: "6px 8px 6px 0",
          borderRadius: 4,
        }}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
        role="button"
        tabIndex={0}
      >
        <span
          style={{
            color: "#8c8c8c",
            fontSize: 12,
            minWidth: 44,
            paddingTop: 2,
          }}
        >
          {formatServerHourMinute(group.timestamp, timeZone)}
        </span>
        <span
          style={{
            position: "relative",
            left: -11,
            marginRight: -6,
            marginTop: 6,
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: dotColor,
            border: "2px solid #fff",
            boxShadow: "0 0 0 1px #d9d9d9",
            flex: "0 0 10px",
          }}
        />
        <div style={{ flex: 1, minWidth: 0, fontSize: 13 }}>
          <Space size={6} wrap>
            <span style={{ color: "#262626" }}>📥 {summary.title}</span>
            {summary.tags.map((t, idx) => (
              <Tag key={idx} color={t.color} style={{ margin: 0 }}>
                {t.text}
              </Tag>
            ))}
          </Space>
        </div>
        <span style={{ color: "#bfbfbf", fontSize: 12, paddingTop: 2 }}>
          {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
      </div>
      {isExpanded && (
        <div
          style={{
            paddingLeft: 60,
            paddingRight: 8,
            paddingBottom: 6,
            borderLeft: "1px dashed transparent",
          }}
        >
          {group.items.map((j) => (
            <DetailLine key={j.id} item={j} timeZone={timeZone} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Standalone key event: promote / reject / deprecate / create / update / merge. */
function SingleEventRow({
  item,
  timeZone,
}: {
  item: JournalItem;
  timeZone: string;
}) {
  const { t, i18n } = useTranslation();
  const isZh = i18n.language?.startsWith("zh") ?? false;
  const dotColor = ACTION_HEX[item.action] ?? "#bfbfbf";
  const story = singleEventStory(item);
  const isRun = item.action === "extract_run";
  const runText = isRun ? extractRunSummary(item.after, t) : "";
  const detailText = isRun ? "" : noteToDisplay(item.note, t, isZh);
  return (
    <div style={{ marginBottom: 10, display: "flex", gap: 12 }}>
      <span
        style={{
          color: "#8c8c8c",
          fontSize: 12,
          minWidth: 44,
          paddingTop: 2,
        }}
      >
        {formatServerHourMinute(item.timestamp, timeZone)}
      </span>
      <span
        style={{
          position: "relative",
          left: -11,
          marginRight: -6,
          marginTop: 6,
          width: 10,
          height: 10,
          borderRadius: "50%",
          background: dotColor,
          border: "2px solid #fff",
          boxShadow: "0 0 0 1px #d9d9d9",
          flex: "0 0 10px",
        }}
      />
      <div style={{ flex: 1, minWidth: 0, fontSize: 13 }}>
        <Space size={6} wrap>
          <span style={{ color: "#262626" }}>{story.icon}</span>
          <Tag
            color={ACTION_COLOR[item.action] ?? "default"}
            style={{ margin: 0 }}
          >
            {actionLabel(item.action, t)}
          </Tag>
          <span style={{ color: "#595959" }}>
            {isRun ? runText : targetText(item, t)}
          </span>
        </Space>
        {detailText ? (
          <div
            style={{
              marginTop: 4,
              fontSize: 12,
              color: "#8c8c8c",
              lineHeight: 1.5,
            }}
          >
            {detailText}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Human summary for an ``extract_run`` row, built from its structured stats. */
function extractRunSummary(
  after: ExtractRunStats | null | undefined,
  t: TFunction,
): string {
  const s = after ?? {};
  if (s.failure_reason) {
    if (/no llm|not configured|no model/i.test(s.failure_reason)) {
      return t("memory.journal.summary.noModel");
    }
    return t("memory.journal.summary.failed");
  }
  const extracted = s.events_extracted ?? 0;
  if (extracted === 0) {
    return t("memory.journal.summary.scanned", {
      n: s.events_considered ?? 0,
    });
  }
  const promoted = s.promoted ?? 0;
  const candidates = s.candidates ?? 0;
  if (candidates === 0) {
    return t("memory.journal.summary.processedNone", { n: extracted });
  }
  return t("memory.journal.summary.processed", {
    extracted,
    candidates,
    promoted,
  });
}

/** Child row for each pipeline detail in the expanded state. */
function DetailLine({
  item,
  timeZone,
}: {
  item: JournalItem;
  timeZone: string;
}) {
  const { t, i18n } = useTranslation();
  const isZh = i18n.language?.startsWith("zh") ?? false;
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "baseline",
        padding: "3px 0",
        fontSize: 12,
        color: "#8c8c8c",
      }}
    >
      <span style={{ minWidth: 40 }}>
        {formatServerHourMinute(item.timestamp, timeZone)}
      </span>
      <Tag
        color={ACTION_COLOR[item.action] ?? "default"}
        style={{ margin: 0, fontSize: 11 }}
      >
        {actionLabel(item.action, t)}
      </Tag>
      {targetText(item, t) ? (
        <span style={{ color: "#8c8c8c" }}>{targetText(item, t)}</span>
      ) : null}
      {noteToDisplay(item.note, t, isZh) ? (
        <span style={{ color: "#bfbfbf" }}>
          — {noteToDisplay(item.note, t, isZh)}
        </span>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data shaping: flat items -> DayBucket[Group[]].
// ---------------------------------------------------------------------------

function buildDays(
  items: JournalItem[],
  timeZone: string,
  t: TFunction,
): DayBucket[] {
  const groups = aggregate(items);
  const out: DayBucket[] = [];
  for (const g of groups) {
    const diffDays = calendarDaysAgo(g.timestamp, timeZone);
    let label: string;
    if (diffDays === 0) label = t("memory.time.today");
    else if (diffDays === 1) label = t("memory.time.yesterday");
    else if (diffDays > 1 && diffDays < 7)
      label = t("memory.time.daysAgo", { n: diffDays });
    else label = formatServerYmd(g.timestamp, timeZone);

    const last = out[out.length - 1];
    if (last && last.label === label) {
      last.groups.push(g);
    } else {
      out.push({ label, groups: [g] });
    }
  }
  return out;
}

/**
 * Aggregation rules:
 *   - Backend list is already timestamp DESC.
 *   - Scan forward; PIPELINE_ACTIONS start or join a group within GROUP_GAP_MS.
 *   - Non-pipeline key events become standalone groups.
 */
function aggregate(items: JournalItem[]): Group[] {
  const groups: Group[] = [];
  let cur: Group | null = null;
  for (const it of items) {
    const isPipeline = PIPELINE_ACTIONS.has(it.action);
    if (!isPipeline) {
      if (cur) {
        groups.push(cur);
        cur = null;
      }
      groups.push({
        key: `single-${it.id}`,
        timestamp: it.timestamp,
        items: [it],
        isPipelineGroup: false,
      });
      continue;
    }
    // pipeline action
    if (!cur) {
      cur = {
        key: `grp-${it.id}`,
        timestamp: it.timestamp,
        items: [it],
        isPipelineGroup: true,
      };
      continue;
    }
    const last = cur.items[cur.items.length - 1];
    const gap = Math.abs(
      new Date(last.timestamp).getTime() - new Date(it.timestamp).getTime(),
    );
    if (gap <= GROUP_GAP_MS) {
      cur.items.push(it);
    } else {
      groups.push(cur);
      cur = {
        key: `grp-${it.id}`,
        timestamp: it.timestamp,
        items: [it],
        isPipelineGroup: true,
      };
    }
  }
  if (cur) groups.push(cur);
  return groups;
}

// ---------------------------------------------------------------------------
// Copy generation.
// ---------------------------------------------------------------------------

interface PipelineSummary {
  title: string;
  tags: { text: string; color: string }[];
}

function pipelineSummary(items: JournalItem[], t: TFunction): PipelineSummary {
  let captureN = 0;
  let extractN = 0;
  let regenN = 0;
  for (const it of items) {
    if (it.action === "capture") captureN++;
    else if (it.action === "extract") extractN++;
    else if (it.action === "page_regen") regenN++;
  }
  let title = t("memory.journal.title.tidied");
  if (captureN > 0 && extractN === 0 && regenN === 0) {
    title = t("memory.journal.title.captured", { n: captureN });
  } else if (captureN > 0 && extractN > 0 && regenN === 0) {
    title = t("memory.journal.title.processed", {
      c: captureN,
      e: extractN,
    });
  } else if (captureN === 0 && extractN > 0 && regenN === 0) {
    title = t("memory.journal.title.extracted", { n: extractN });
  } else if (regenN > 0 && extractN === 0 && captureN === 0) {
    title = t("memory.journal.title.regen", { n: regenN });
  } else if (captureN > 0 && regenN > 0) {
    title = t("memory.journal.title.processedRegen", {
      c: captureN,
      r: regenN,
    });
  } else if (extractN > 0 && regenN > 0) {
    title = t("memory.journal.title.extractedRegen", {
      e: extractN,
      r: regenN,
    });
  }
  const tags: { text: string; color: string }[] = [];
  if (captureN > 0)
    tags.push({
      text: t("memory.journal.tag.conversations", { n: captureN }),
      color: "default",
    });
  if (extractN > 0)
    tags.push({
      text: t("memory.journal.tag.drafts", { n: extractN }),
      color: "blue",
    });
  if (regenN > 0)
    tags.push({
      text: t("memory.journal.tag.refreshes", { n: regenN }),
      color: "geekblue",
    });
  return { title, tags };
}

function singleEventStory(item: JournalItem): { icon: string } {
  switch (item.action) {
    case "extract_run":
      return { icon: item.after?.failure_reason ? "⚠️" : "🔍" };
    case "promote":
      return { icon: "✅" };
    case "reject":
      return { icon: "🚫" };
    case "deprecate":
      return { icon: "🗑️" };
    case "create":
      return { icon: "🆕" };
    case "update":
    case "user_edit":
      return { icon: "✏️" };
    case "merge":
      return { icon: "🔗" };
    default:
      return { icon: "•" };
  }
}

function targetText(j: JournalItem, t: TFunction): string {
  // Backend-enriched target text lets us show the specific acted-on item; otherwise fall back to type.
  if (j.target_summary)
    return t("memory.journal.targetQuoted", { text: j.target_summary });
  if (j.target_atom_id) return t("memory.journal.targetAtom");
  if (j.target_entity_id) return t("memory.journal.targetEntity");
  if (j.target_candidate_id) return t("memory.journal.targetCandidate");
  return "";
}

function actionLabel(action: string, t: TFunction): string {
  switch (action) {
    case "extract_run":
      return t("memory.journal.action.extractRun");
    case "capture":
      return t("memory.journal.action.capture");
    case "extract":
      return t("memory.journal.action.extract");
    case "promote":
      return t("memory.journal.action.promote");
    case "reject":
      return t("memory.journal.action.reject");
    case "deprecate":
      return t("memory.journal.action.deprecate");
    case "page_regen":
      return t("memory.journal.filter.pageRegen");
    case "create":
      return t("memory.journal.action.create");
    case "update":
    case "user_edit":
      return t("memory.journal.action.update");
    case "merge":
      return t("memory.journal.action.merge");
    default:
      return action;
  }
}

/**
 * Turn backend notes — often English dev logs — into user-facing text.
 * Known English patterns are localized, user-provided Chinese reasons are
 * preserved, and other dev logs return null to avoid mixed-language noise.
 */
function noteToDisplay(
  note: string | null | undefined,
  t: TFunction,
  isZh: boolean,
): string | null {
  const s = (note ?? "").trim();
  if (!s) return null;

  // Entity resolution during promotion: linked existing topic or created new topic.
  let m = /^entity resolved via alias ['"](.+)['"]$/i.exec(s);
  if (m) return t("memory.journal.note.entityResolved", { name: m[1] });
  m = /^no existing entity matched ['"](.+)['"];?\s*will create$/i.exec(s);
  if (m) return t("memory.journal.note.entityCreated", { name: m[1] });

  // Deprecation-related notes.
  if (/^atom deprecated without replacement/i.test(s))
    return t("memory.journal.note.deprecatedNoReplacement");
  m = /^semantic duplicate; superseded by /i.exec(s);
  if (m) return t("memory.journal.note.semanticDuplicate");

  // Chinese notes (e.g. user-provided reasons) pass through in either locale.
  if (/[一-鿿]/.test(s)) return s;

  // In the English UI the raw note is already readable — show it as-is.
  if (!isZh) return s;

  // Hide other English dev logs from the Chinese UI.
  return null;
}
