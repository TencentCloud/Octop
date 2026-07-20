/**
 * AtomsList.tsx — paginated list of memories with a detail drawer.
 *
 * Uses a combined user-facing view: type filters instead of technical kind tags,
 * star importance, percentage confidence, relative timestamps, and no raw metadata IDs.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Progress,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  memoryDashboardApi,
  isAtomDeprecated,
  type AtomItem,
  type AtomKind,
  type Importance,
  type ListAtomsBody,
} from "../../../api/modules/memoryDashboard";
import MemoryLayerView from "./shared/MemoryLayerView";
import LineageStrip from "./shared/LineageStrip";
import MemoryPipelineEmpty from "./shared/MemoryPipelineEmpty";
import { confirmDeprecateAtom } from "./shared/deprecateAtom";

const PAGE_SIZE = 20;

// Type filter: map backend enum values to user-facing labels.
const KIND_OPTIONS: { value: AtomKind | ""; label: string }[] = [
  { value: "", label: "全部类型" },
  { value: "Fact", label: "事实" },
  { value: "Decision", label: "决定" },
  { value: "Task", label: "任务" },
  { value: "Preference", label: "偏好" },
  { value: "ConflictCandidate", label: "可能矛盾" },
];

const IMPORTANCE_OPTIONS: { value: Importance | ""; label: string }[] = [
  { value: "", label: "全部" },
  { value: "low", label: "一般" },
  { value: "medium", label: "重要" },
  { value: "high", label: "非常重要" },
];

interface Props {
  agentId: string;
}

export default function AtomsList({ agentId }: Props) {
  const { t } = useTranslation();
  const [items, setItems] = useState<AtomItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<AtomKind | "">("");
  const [importance, setImportance] = useState<Importance | "">("");
  const [selected, setSelected] = useState<AtomItem | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const body: ListAtomsBody = {
      offset: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    };
    if (kind) body.candidate_type = kind;
    if (importance) body.importance_min = importance;
    try {
      const r = await memoryDashboardApi.listAtoms(agentId, body);
      setItems(r.items);
      setTotal(r.total);
    } finally {
      setLoading(false);
    }
  }, [agentId, page, kind, importance]);

  useEffect(() => {
    if (!agentId) return;
    void load();
  }, [agentId, load]);

  const handleDeprecate = (atom: AtomItem) => {
    confirmDeprecateAtom({
      agentId,
      atom,
      onSuccess: () => {
        setSelected(null);
        void load();
      },
    });
  };

  const toolbar = (
    <>
      <span style={{ color: "#595959" }}>{t("memory.list.kind", "类型")}:</span>
      <Select
        style={{ width: 160 }}
        value={kind}
        onChange={(v) => {
          setKind(v);
          setPage(1);
        }}
        options={KIND_OPTIONS}
      />
      <span style={{ color: "#595959" }}>
        {t("memory.list.importanceMin", "重要程度不低于")}:
      </span>
      <Select
        style={{ width: 140 }}
        value={importance}
        onChange={(v) => {
          setImportance(v);
          setPage(1);
        }}
        options={IMPORTANCE_OPTIONS}
      />
    </>
  );

  // Guided empty only when no filter is active — a filtered-out list must
  // keep the plain empty so it doesn't read as "distillation pending".
  const noFilterActive = !kind && !importance;

  return (
    <MemoryLayerView<AtomItem>
      toolbar={toolbar}
      items={items}
      total={total}
      page={page}
      pageSize={PAGE_SIZE}
      onPageChange={setPage}
      loading={loading}
      emptyContent={
        noFilterActive ? <MemoryPipelineEmpty agentId={agentId} /> : undefined
      }
      keyOf={(a) => a.id}
      selected={selected}
      onItemClick={setSelected}
      onCloseDrawer={() => setSelected(null)}
      drawerTitle={t("memory.atomDetail", "记忆详情")}
      drawerWidth={560}
      renderItem={(a) => (
        <div
          style={{
            position: "relative",
            paddingRight: isAtomDeprecated(a) ? 0 : 32,
          }}
          onMouseEnter={() => setHoveredId(a.id)}
          onMouseLeave={() => setHoveredId(null)}
        >
          <Space size={4}>
            <ImportanceStars importance={a.importance} />
            {isAtomDeprecated(a) ? <Tag color="red">已忘记</Tag> : null}
          </Space>
          <div style={{ marginTop: 4, fontSize: 13 }}>{a.assertion}</div>
          <div style={{ marginTop: 2, fontSize: 12, color: "#8c8c8c" }}>
            {formatRelativeTime(a.created_at)}
            {a.kind ? ` · ${kindLabel(a.kind)}` : ""}
          </div>
          {!isAtomDeprecated(a) && hoveredId === a.id ? (
            <Tooltip title="弃用这条记忆">
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeprecate(a);
                }}
                style={{
                  position: "absolute",
                  right: 0,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "#ff4d4f",
                  cursor: "pointer",
                  fontSize: 15,
                  padding: "2px 4px",
                  borderRadius: 4,
                  lineHeight: 1,
                }}
              >
                <Trash2 size={14} />
              </span>
            </Tooltip>
          ) : null}
        </div>
      )}
      renderDrawer={(atom) => (
        <div>
          <Space size={8} wrap style={{ marginBottom: 12 }}>
            {atom.kind ? <Tag>{kindLabel(atom.kind)}</Tag> : null}
            <ImportanceStars importance={atom.importance} />
            <Tag color={isAtomDeprecated(atom) ? "red" : "green"}>
              {isAtomDeprecated(atom) ? "已忘记" : "在用"}
            </Tag>
          </Space>

          {/* Source, shown only as user-facing lineage after view consolidation */}
          <LineageStrip agentId={agentId} atom={atom} />

          <Typography.Title level={5}>记忆内容</Typography.Title>
          <Typography.Paragraph>{atom.assertion}</Typography.Paragraph>

          <Typography.Title level={5}>原话依据</Typography.Title>
          <Typography.Paragraph type="secondary">
            {atom.verbatim_quote}
          </Typography.Paragraph>

          <Typography.Title level={5}>可信度</Typography.Title>
          <ConfidenceBar confidence={atom.confidence} />

          {(atom.search_terms ?? []).length > 0 ? (
            <>
              <Typography.Title level={5} style={{ marginTop: 12 }}>
                关联关键词
              </Typography.Title>
              <Space size={4} wrap>
                {(atom.search_terms ?? []).map((s) => (
                  <Tag key={s}>{s}</Tag>
                ))}
              </Space>
            </>
          ) : null}

          <Typography.Paragraph
            type="secondary"
            style={{ fontSize: 12, marginTop: 16 }}
          >
            首次记录于 {formatRelativeTime(atom.created_at)}
            {atom.occurred_at
              ? ` · 发生于 ${formatRelativeTime(atom.occurred_at)}`
              : ""}
          </Typography.Paragraph>

          {/* Actions, shown only for active atoms */}
          {!isAtomDeprecated(atom) ? (
            <>
              <Typography.Title level={5} style={{ marginTop: 12 }}>
                操作
              </Typography.Title>
              <Button danger onClick={() => handleDeprecate(atom)}>
                弃用这条记忆
              </Button>
            </>
          ) : null}
        </div>
      )}
    />
  );
}

// ---------------------------------------------------------------------------
// Visual helpers
// ---------------------------------------------------------------------------

function kindLabel(k: string): string {
  switch (k) {
    case "Fact":
      return "事实";
    case "Decision":
      return "决定";
    case "Task":
      return "任务";
    case "Preference":
      return "偏好";
    case "ConflictCandidate":
      return "可能矛盾";
    default:
      return k;
  }
}

function ImportanceStars({ importance }: { importance: string }) {
  const n = importance === "high" ? 3 : importance === "medium" ? 2 : 1;
  return (
    <span
      title={`重要程度：${
        importance === "high"
          ? "非常重要"
          : importance === "medium"
          ? "重要"
          : "一般"
      }`}
      style={{ color: "#faad14", fontSize: 13, letterSpacing: 1 }}
    >
      {"★".repeat(n)}
      <span style={{ color: "#d9d9d9" }}>{"★".repeat(3 - n)}</span>
    </span>
  );
}

function ConfidenceBar({ confidence }: { confidence: string }) {
  const pct = confidence === "high" ? 90 : confidence === "medium" ? 60 : 30;
  const label =
    confidence === "high"
      ? "很有把握"
      : confidence === "medium"
      ? "一般把握"
      : "不太确定";
  return (
    <div style={{ maxWidth: 320 }}>
      <Progress
        percent={pct}
        size="small"
        strokeColor={
          confidence === "high"
            ? "#52c41a"
            : confidence === "medium"
            ? "#faad14"
            : "#ff7875"
        }
        format={() => label}
      />
    </div>
  );
}

function formatRelativeTime(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - then) / 1000));
    if (diffSec < 60) return "刚刚";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} 小时前`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay} 天前`;
    const diffMonth = Math.floor(diffDay / 30);
    if (diffMonth < 12) return `${diffMonth} 个月前`;
    return `${Math.floor(diffMonth / 12)} 年前`;
  } catch {
    return iso;
  }
}
