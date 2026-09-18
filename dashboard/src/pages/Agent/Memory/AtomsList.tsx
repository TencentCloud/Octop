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
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  memoryDashboardApi,
  isAtomDeprecated,
  type AtomItem,
  type AtomKind,
  type EntityItem,
  type Importance,
  type ListAtomsBody,
} from "../../../api/modules/memoryDashboard";
import MemoryLayerView from "./shared/MemoryLayerView";
import LineageStrip from "./shared/LineageStrip";
import MemoryPipelineEmpty from "./shared/MemoryPipelineEmpty";
import { confirmDeprecateAtom } from "./shared/deprecateAtom";
import { confirmEditAtom } from "./shared/editAtom";
import CreateAtomModal from "./shared/createAtom";

const PAGE_SIZE = 20;

// Type filter: map backend enum values to user-facing labels.
const kindOptions = (t: TFunction) =>
  [
    { value: "", label: t("memory.candidates.kindAll") },
    { value: "Fact", label: t("memory.kind.fact") },
    { value: "Decision", label: t("memory.kind.decision") },
    { value: "Task", label: t("memory.kind.task") },
    { value: "Preference", label: t("memory.kind.preference") },
    { value: "ConflictCandidate", label: t("memory.kind.conflict") },
  ] as { value: AtomKind | ""; label: string }[];

const importanceOptions = (t: TFunction) =>
  [
    { value: "", label: t("memory.candidates.status.all") },
    { value: "low", label: t("memory.tree.importanceLow") },
    { value: "medium", label: t("memory.tree.importanceMedium") },
    { value: "high", label: t("memory.tree.importanceHigh") },
  ] as { value: Importance | ""; label: string }[];

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
  const [entities, setEntities] = useState<EntityItem[]>([]);
  const [createOpen, setCreateOpen] = useState(false);

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
    void memoryDashboardApi
      .listEntities(agentId, {
        limit: 200,
        order_by: "atom_count",
        order: "desc",
      })
      .then((r) => setEntities(r.items))
      .catch(() => setEntities([]));
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

  const handleEdit = (atom: AtomItem) => {
    confirmEditAtom({
      agentId,
      atom,
      onSuccess: (next) => {
        setSelected(next);
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
        options={kindOptions(t)}
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
        options={importanceOptions(t)}
      />
      <Button
        size="small"
        icon={<Plus size={14} />}
        onClick={() => setCreateOpen(true)}
      >
        {t("memory.create.title", "新建记忆")}
      </Button>
    </>
  );

  // Guided empty only when no filter is active — a filtered-out list must
  // keep the plain empty so it doesn't read as "distillation pending".
  const noFilterActive = !kind && !importance;

  return (
    <>
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
              paddingRight: isAtomDeprecated(a) ? 0 : 56,
            }}
            onMouseEnter={() => setHoveredId(a.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            <Space size={4}>
              <ImportanceStars importance={a.importance} />
              {isAtomDeprecated(a) ? (
                <Tag color="red">{t("memory.tree.deprecatedTag")}</Tag>
              ) : null}
            </Space>
            <div style={{ marginTop: 4, fontSize: 13 }}>{a.assertion}</div>
            <div style={{ marginTop: 2, fontSize: 12, color: "#8c8c8c" }}>
              {formatRelativeTime(a.created_at, t)}
              {a.kind ? ` · ${kindLabel(a.kind, t)}` : ""}
            </div>
            {!isAtomDeprecated(a) && hoveredId === a.id ? (
              <span
                style={{
                  position: "absolute",
                  right: 0,
                  top: "50%",
                  transform: "translateY(-50%)",
                  display: "inline-flex",
                  gap: 4,
                }}
              >
                <Tooltip title={t("memory.edit.tooltip", "编辑这条记忆")}>
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      handleEdit(a);
                    }}
                    style={{
                      color: "#1677ff",
                      cursor: "pointer",
                      padding: "2px 4px",
                      borderRadius: 4,
                      lineHeight: 1,
                    }}
                  >
                    <Pencil size={14} />
                  </span>
                </Tooltip>
                <Tooltip
                  title={t("memory.tree.deprecateTooltip", "弃用这条记忆")}
                >
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeprecate(a);
                    }}
                    style={{
                      color: "#ff4d4f",
                      cursor: "pointer",
                      padding: "2px 4px",
                      borderRadius: 4,
                      lineHeight: 1,
                    }}
                  >
                    <Trash2 size={14} />
                  </span>
                </Tooltip>
              </span>
            ) : null}
          </div>
        )}
        renderDrawer={(atom) => (
          <div>
            <Space size={8} wrap style={{ marginBottom: 12 }}>
              {atom.kind ? <Tag>{kindLabel(atom.kind, t)}</Tag> : null}
              <ImportanceStars importance={atom.importance} />
              <Tag color={isAtomDeprecated(atom) ? "red" : "green"}>
                {isAtomDeprecated(atom)
                  ? t("memory.tree.deprecatedTag")
                  : t("memory.tree.activeTag")}
              </Tag>
            </Space>

            <LineageStrip agentId={agentId} atom={atom} />

            <Typography.Title level={5}>
              {t("memory.tree.assertionTitle")}
            </Typography.Title>
            <Typography.Paragraph>{atom.assertion}</Typography.Paragraph>

            <Typography.Title level={5}>
              {t("memory.candidates.verbatimTitle")}
            </Typography.Title>
            <Typography.Paragraph type="secondary">
              {atom.verbatim_quote}
            </Typography.Paragraph>

            <Typography.Title level={5}>
              {t("memory.tree.confidenceTitle")}
            </Typography.Title>
            <ConfidenceBar confidence={atom.confidence} />

            {(atom.search_terms ?? []).length > 0 ? (
              <>
                <Typography.Title level={5} style={{ marginTop: 12 }}>
                  {t("memory.tree.searchTermsTitle")}
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
              {t("memory.tree.firstRecorded", {
                time: formatRelativeTime(atom.created_at, t),
              })}
              {atom.occurred_at
                ? t("memory.tree.occurredAt", {
                    time: formatRelativeTime(atom.occurred_at, t),
                  })
                : ""}
            </Typography.Paragraph>

            {!isAtomDeprecated(atom) ? (
              <>
                <Typography.Title level={5} style={{ marginTop: 12 }}>
                  {t("memory.tree.actions", "操作")}
                </Typography.Title>
                <Space>
                  <Button onClick={() => handleEdit(atom)}>
                    {t("memory.edit.action", "编辑这条记忆")}
                  </Button>
                  <Button danger onClick={() => handleDeprecate(atom)}>
                    {t("memory.tree.deprecate", "弃用这条记忆")}
                  </Button>
                </Space>
              </>
            ) : null}
          </div>
        )}
      />
      <CreateAtomModal
        open={createOpen}
        agentId={agentId}
        entities={entities}
        onClose={() => setCreateOpen(false)}
        onSuccess={() => {
          void load();
          void memoryDashboardApi
            .listEntities(agentId, {
              limit: 200,
              order_by: "atom_count",
              order: "desc",
            })
            .then((r) => setEntities(r.items))
            .catch(() => undefined);
        }}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Visual helpers
// ---------------------------------------------------------------------------

function kindLabel(k: string, t: TFunction): string {
  switch (k) {
    case "Fact":
      return t("memory.kind.fact");
    case "Decision":
      return t("memory.kind.decision");
    case "Task":
      return t("memory.kind.task");
    case "Preference":
      return t("memory.kind.preference");
    case "ConflictCandidate":
      return t("memory.kind.conflict");
    default:
      return k;
  }
}

function ImportanceStars({ importance }: { importance: string }) {
  const { t } = useTranslation();
  const n = importance === "high" ? 3 : importance === "medium" ? 2 : 1;
  return (
    <span
      title={t("memory.tree.importanceTag", {
        v:
          importance === "high"
            ? t("memory.tree.importanceHigh")
            : importance === "medium"
            ? t("memory.tree.importanceMedium")
            : t("memory.tree.importanceLow"),
      })}
      style={{ color: "#faad14", fontSize: 13, letterSpacing: 1 }}
    >
      {"★".repeat(n)}
      <span style={{ color: "#d9d9d9" }}>{"★".repeat(3 - n)}</span>
    </span>
  );
}

function ConfidenceBar({ confidence }: { confidence: string }) {
  const { t } = useTranslation();
  const pct = confidence === "high" ? 90 : confidence === "medium" ? 60 : 30;
  const label =
    confidence === "high"
      ? t("memory.tree.confidenceHigh")
      : confidence === "medium"
      ? t("memory.tree.confidenceMedium")
      : t("memory.tree.confidenceLow");
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

function formatRelativeTime(iso: string, t: TFunction): string {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - then) / 1000));
    if (diffSec < 60) return t("memory.time.justNow");
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return t("memory.time.minutesAgo", { n: diffMin });
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return t("memory.time.hoursAgo", { n: diffHr });
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return t("memory.time.daysAgo", { n: diffDay });
    const diffMonth = Math.floor(diffDay / 30);
    if (diffMonth < 12) return t("memory.time.monthsAgo", { n: diffMonth });
    return t("memory.time.yearsAgo", { n: Math.floor(diffMonth / 12) });
  } catch {
    return iso;
  }
}
