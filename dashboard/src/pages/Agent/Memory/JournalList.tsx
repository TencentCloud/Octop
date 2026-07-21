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

const ACTION_OPTIONS = [
  { value: "", label: "全部记录" },
  { value: "extract_run", label: "提取运行" },
  { value: "promote", label: "采纳" },
  { value: "reject", label: "忽略" },
  { value: "deprecate", label: "弃用" },
  { value: "page_regen", label: "刷新主题" },
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

  const days = useMemo(() => buildDays(items, timeZone), [items, timeZone]);

  return (
    <Card size="small">
      <Space style={{ marginBottom: 16 }} wrap>
        <span style={{ color: "#595959" }}>筛选类型:</span>
        <Select
          style={{ width: 180 }}
          value={action}
          onChange={(v) => {
            setAction(v);
            setPage(1);
          }}
          options={ACTION_OPTIONS}
        />
      </Space>

      {loading && items.length === 0 ? (
        <Skeleton active />
      ) : items.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无整理记录"
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
          · {day.groups.length} 项
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
  const summary = pipelineSummary(group.items);
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
  const dotColor = ACTION_HEX[item.action] ?? "#bfbfbf";
  const story = singleEventStory(item);
  const isRun = item.action === "extract_run";
  const runText = isRun ? extractRunSummary(item.after) : "";
  const detailText = isRun ? "" : noteToChinese(item.note);
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
            {actionLabel(item.action)}
          </Tag>
          <span style={{ color: "#595959" }}>
            {isRun ? runText : targetText(item)}
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
function extractRunSummary(after: ExtractRunStats | null | undefined): string {
  const s = after ?? {};
  if (s.failure_reason) {
    if (/no llm|not configured|no model/i.test(s.failure_reason)) {
      return "未配置提取模型，本次未运行";
    }
    return "本次提取失败";
  }
  const extracted = s.events_extracted ?? 0;
  if (extracted === 0) {
    return `扫描 ${s.events_considered ?? 0} 段对话，无新增内容`;
  }
  const promoted = s.promoted ?? 0;
  const candidates = s.candidates ?? 0;
  if (candidates === 0) {
    return `处理 ${extracted} 段对话，未发现可记忆的内容`;
  }
  return `处理 ${extracted} 段对话，生成 ${candidates} 条草稿，晋升 ${promoted} 条记忆`;
}

/** Child row for each pipeline detail in the expanded state. */
function DetailLine({
  item,
  timeZone,
}: {
  item: JournalItem;
  timeZone: string;
}) {
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
        {actionLabel(item.action)}
      </Tag>
      {targetText(item) ? (
        <span style={{ color: "#8c8c8c" }}>{targetText(item)}</span>
      ) : null}
      {noteToChinese(item.note) ? (
        <span style={{ color: "#bfbfbf" }}>— {noteToChinese(item.note)}</span>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data shaping: flat items -> DayBucket[Group[]].
// ---------------------------------------------------------------------------

function buildDays(items: JournalItem[], timeZone: string): DayBucket[] {
  const groups = aggregate(items);
  const out: DayBucket[] = [];
  for (const g of groups) {
    const diffDays = calendarDaysAgo(g.timestamp, timeZone);
    let label: string;
    if (diffDays === 0) label = "今天";
    else if (diffDays === 1) label = "昨天";
    else if (diffDays > 1 && diffDays < 7) label = `${diffDays} 天前`;
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

function pipelineSummary(items: JournalItem[]): PipelineSummary {
  let captureN = 0;
  let extractN = 0;
  let regenN = 0;
  for (const it of items) {
    if (it.action === "capture") captureN++;
    else if (it.action === "extract") extractN++;
    else if (it.action === "page_regen") regenN++;
  }
  let title = "整理了一段对话";
  if (captureN > 0 && extractN === 0 && regenN === 0) {
    title = `记录了 ${captureN} 段对话`;
  } else if (captureN > 0 && extractN > 0 && regenN === 0) {
    title = `处理了 ${captureN} 段对话，生成 ${extractN} 条记忆草稿`;
  } else if (captureN === 0 && extractN > 0 && regenN === 0) {
    title = `生成了 ${extractN} 条记忆草稿`;
  } else if (regenN > 0 && extractN === 0 && captureN === 0) {
    title = `刷新了 ${regenN} 个主题摘要`;
  } else if (captureN > 0 && regenN > 0) {
    title = `处理了 ${captureN} 段对话，并刷新了 ${regenN} 个主题摘要`;
  } else if (extractN > 0 && regenN > 0) {
    title = `生成了 ${extractN} 条记忆草稿，并刷新了 ${regenN} 个主题摘要`;
  }
  const tags: { text: string; color: string }[] = [];
  if (captureN > 0)
    tags.push({ text: `📥 ${captureN} 段对话`, color: "default" });
  if (extractN > 0) tags.push({ text: `📝 ${extractN} 条草稿`, color: "blue" });
  if (regenN > 0) tags.push({ text: `🔄 ${regenN} 次刷新`, color: "geekblue" });
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
      return { icon: "✏️" };
    case "merge":
      return { icon: "🔗" };
    default:
      return { icon: "•" };
  }
}

function targetText(j: JournalItem): string {
  // Backend-enriched target text lets us show the specific acted-on item; otherwise fall back to type.
  if (j.target_summary) return `「${j.target_summary}」`;
  if (j.target_atom_id) return "一条记忆";
  if (j.target_entity_id) return "一个主题";
  if (j.target_candidate_id) return "一条草稿";
  return "";
}

function actionLabel(action: string): string {
  switch (action) {
    case "extract_run":
      return "提取运行";
    case "capture":
      return "记录对话";
    case "extract":
      return "生成草稿";
    case "promote":
      return "采纳";
    case "reject":
      return "忽略";
    case "deprecate":
      return "弃用";
    case "page_regen":
      return "刷新主题";
    case "create":
      return "创建";
    case "update":
      return "更新";
    case "merge":
      return "合并";
    default:
      return action;
  }
}

/**
 * Convert backend notes, often English dev logs, into user-facing Chinese.
 * Known English patterns are translated, user-provided Chinese reasons are
 * preserved, and other dev logs return null to avoid mixed-language noise.
 */
function noteToChinese(note: string | null | undefined): string | null {
  const s = (note ?? "").trim();
  if (!s) return null;

  // Entity resolution during promotion: linked existing topic or created new topic.
  let m = /^entity resolved via alias ['"](.+)['"]$/i.exec(s);
  if (m) return `关联到已有主题「${m[1]}」`;
  m = /^no existing entity matched ['"](.+)['"];?\s*will create$/i.exec(s);
  if (m) return `新建主题「${m[1]}」`;

  // Deprecation-related notes.
  if (/^atom deprecated without replacement/i.test(s))
    return "弃用（无替代记忆）";
  m = /^semantic duplicate; superseded by /i.exec(s);
  if (m) return "语义重复，已被合并";

  // Preserve user-provided Chinese reasons.
  if (/[一-鿿]/.test(s)) return s;

  // Hide other English dev logs.
  return null;
}
