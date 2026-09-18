/**
 * MemoryTree.tsx — VSCode-style indented tree view of Entity → Atom.
 *
 * Layout (form B + indented list, locked in 2026-06-29 brainstorming):
 *   ▼ Agent (root)
 *     ▼ 🏷️ Entity A                    [12 atoms]
 *         high-confidence atom text... · relative time
 *         medium-confidence atom...    · relative time
 *     ▶ 🏷️ Entity B                    [5 atoms]
 *
 * Data strategy (lazy loading):
 *   - First paint: listEntities() once.
 *   - Click an entity row → listAtoms({entity_id}) lazily, cached in
 *     a `Map<entityId, AtomItem[]>`. Re-collapse keeps cache.
 *
 * Interactions:
 *   - Click entity row → toggle expand/collapse + lazy fetch.
 *   - Click atom row   → opens right-side detail drawer with full metadata.
 *
 * Confidence colour dots (atom row inline):
 *   high → 🟢 / medium → 🟡 / low → 🔴
 *
 * The drawer reuses the same fields as AtomsList' drawer for consistency.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Skeleton,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  memoryDashboardApi,
  isAtomDeprecated,
  type AtomItem,
  type Confidence,
  type EntityDetail,
  type EntityItem,
  type EntityPage,
} from "../../../api/modules/memoryDashboard";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import MemoryPipelineEmpty from "./shared/MemoryPipelineEmpty";
import { confirmDeprecateAtom } from "./shared/deprecateAtom";
import { confirmEditAtom } from "./shared/editAtom";
import CreateAtomModal from "./shared/createAtom";
import LineageStrip from "./shared/LineageStrip";

interface Props {
  agentId: string;
  /** Auto-expand the specified entity when jumping from the profile page. */
  initialExpandEntityId?: string;
}

const ENTITY_LIMIT = 200; // pull all entities up-front; tree view shouldn't paginate
const ATOM_LIMIT = 200; // per entity

type AtomCache = Map<string, { loading: boolean; items: AtomItem[] | null }>;

export default function MemoryTree({ agentId, initialExpandEntityId }: Props) {
  const { t } = useTranslation();

  const [entities, setEntities] = useState<EntityItem[]>([]);
  const [entitiesLoading, setEntitiesLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(
    initialExpandEntityId ? new Set([initialExpandEntityId]) : new Set(),
  );
  const [atomsByEntity, setAtomsByEntity] = useState<AtomCache>(new Map());
  const [selectedAtom, setSelectedAtom] = useState<AtomItem | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createEntityId, setCreateEntityId] = useState<string | undefined>();
  // Entity whose long-form summary page is being viewed in the drawer.
  const [summaryEntity, setSummaryEntity] = useState<EntityItem | null>(null);
  // Used for scroll positioning.
  const targetRowRef = useRef<HTMLLIElement | null>(null);
  // Read the latest atomsByEntity through a ref to avoid useEffect dependency loops.
  const atomsByEntityRef = useRef<AtomCache>(new Map());
  atomsByEntityRef.current = atomsByEntity;

  const loadEntities = useCallback(async () => {
    setEntitiesLoading(true);
    try {
      const r = await memoryDashboardApi.listEntities(agentId, {
        limit: ENTITY_LIMIT,
        order_by: "atom_count",
        order: "desc",
      });
      setEntities(r.items);
    } finally {
      setEntitiesLoading(false);
    }
  }, [agentId]);

  const fetchAtoms = useCallback(
    async (entityId: string) => {
      // mark loading
      setAtomsByEntity((prev) => {
        const next = new Map(prev);
        next.set(entityId, { loading: true, items: null });
        return next;
      });
      try {
        const r = await memoryDashboardApi.listAtoms(agentId, {
          entity_id: entityId,
          limit: ATOM_LIMIT,
          order_by: "importance",
          order: "desc",
        });
        setAtomsByEntity((prev) => {
          const next = new Map(prev);
          next.set(entityId, { loading: false, items: r.items });
          return next;
        });
      } catch {
        setAtomsByEntity((prev) => {
          const next = new Map(prev);
          next.set(entityId, { loading: false, items: [] });
          return next;
        });
      }
    },
    [agentId],
  );

  // When initialExpandEntityId changes or entities finish loading, ensure the target
  // entity is expanded, its atoms are fetched, and the page scrolls to that row.
  useEffect(() => {
    if (!initialExpandEntityId) return;
    // Add the target entity to the expanded set.
    setExpanded((prev) => {
      if (prev.has(initialExpandEntityId)) return prev;
      const next = new Set(prev);
      next.add(initialExpandEntityId);
      return next;
    });
    // Wait when entities are not loaded yet; loading completion will trigger this again.
    if (entitiesLoading || entities.length === 0) return;
    // lazy fetch atoms
    if (!atomsByEntityRef.current.has(initialExpandEntityId)) {
      void fetchAtoms(initialExpandEntityId);
    }
    // Scroll to the target row after the DOM renders.
    setTimeout(() => {
      targetRowRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 300);
  }, [initialExpandEntityId, entitiesLoading, entities.length, fetchAtoms]);

  useEffect(() => {
    if (!agentId) return;
    void loadEntities();
  }, [agentId, loadEntities]);

  const handleToggleEntity = (entityId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(entityId)) {
        next.delete(entityId);
      } else {
        next.add(entityId);
        // lazy load on first expand
        if (!atomsByEntity.has(entityId)) {
          void fetchAtoms(entityId);
        }
      }
      return next;
    });
  };

  const handleRefresh = () => {
    setExpanded(new Set());
    setAtomsByEntity(new Map());
    void loadEntities();
  };

  // After deprecation: close the drawer and reload the owning entity list.
  const handleDeprecated = (atom: AtomItem) => {
    setSelectedAtom(null);
    void fetchAtoms(atom.entity_id);
  };

  const handleReplaced = (next: AtomItem) => {
    setSelectedAtom(next);
    void fetchAtoms(next.entity_id);
  };

  const handleCreated = (atom: AtomItem) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.add(atom.entity_id);
      return next;
    });
    void loadEntities();
    void fetchAtoms(atom.entity_id);
  };

  const totalAtoms = useMemo(
    () => entities.reduce((sum, e) => sum + e.atom_count, 0),
    [entities],
  );

  return (
    <Card size="small">
      {/* Header strip */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
          paddingBottom: 8,
          borderBottom: "1px solid var(--fn-border-primary, #f0f0f0)",
        }}
      >
        <Space size={8}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>
            {t("memory.tree.title")}
          </span>
          <Tag>
            {t("memory.tree.entityCount", "{{n}} 个主题", {
              n: entities.length,
            })}
          </Tag>
          <Tag color="blue">
            {t("memory.tree.atomCount", "{{n}} 条记忆", { n: totalAtoms })}
          </Tag>
        </Space>
        <Space size={12}>
          <Button
            size="small"
            icon={<Plus size={14} />}
            onClick={() => {
              setCreateEntityId(undefined);
              setCreateOpen(true);
            }}
          >
            {t("memory.create.title")}
          </Button>
          <a
            onClick={handleRefresh}
            style={{ fontSize: 12, cursor: "pointer" }}
          >
            <RefreshCw size={14} /> {t("common.refresh")}
          </a>
        </Space>
      </div>

      <div style={{ fontSize: 12, color: "#8c8c8c", marginBottom: 8 }}>
        {t("memory.tree.hint")}
      </div>

      {entitiesLoading && entities.length === 0 ? (
        <Skeleton active />
      ) : entities.length === 0 ? (
        <MemoryPipelineEmpty agentId={agentId} />
      ) : (
        <div className="memory-tree" style={{ fontSize: 13 }}>
          {/* Root row */}
          <RootRow agentId={agentId} entityCount={entities.length} />

          {/* Entities (children of root) */}
          <ul style={listResetStyle}>
            {entities.map((entity) => {
              const isExpanded = expanded.has(entity.id);
              const cache = atomsByEntity.get(entity.id);
              return (
                <li
                  key={entity.id}
                  style={{ position: "relative" }}
                  ref={
                    entity.id === initialExpandEntityId
                      ? targetRowRef
                      : undefined
                  }
                >
                  <EntityRow
                    entity={entity}
                    expanded={isExpanded}
                    onToggle={() => handleToggleEntity(entity.id)}
                    onViewSummary={() => setSummaryEntity(entity)}
                    onAdd={() => {
                      setCreateEntityId(entity.id);
                      setCreateOpen(true);
                    }}
                  />
                  {isExpanded ? (
                    <AtomChildren
                      cache={cache}
                      onSelect={setSelectedAtom}
                      onEdit={(atom) =>
                        confirmEditAtom({
                          agentId,
                          atom,
                          onSuccess: handleReplaced,
                        })
                      }
                      onDeprecate={(atom) =>
                        confirmDeprecateAtom({
                          agentId,
                          atom,
                          onSuccess: () => void fetchAtoms(atom.entity_id),
                        })
                      }
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <AtomDetailDrawer
        open={!!selectedAtom}
        atom={selectedAtom}
        agentId={agentId}
        onClose={() => setSelectedAtom(null)}
        onDeprecated={handleDeprecated}
        onReplaced={handleReplaced}
      />

      <EntitySummaryDrawer
        agentId={agentId}
        entity={summaryEntity}
        onClose={() => setSummaryEntity(null)}
      />

      <CreateAtomModal
        open={createOpen}
        agentId={agentId}
        entities={entities}
        presetEntityId={createEntityId}
        onClose={() => {
          setCreateOpen(false);
          setCreateEntityId(undefined);
        }}
        onSuccess={(atom) => handleCreated(atom)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const listResetStyle: React.CSSProperties = {
  listStyle: "none",
  margin: 0,
  padding: 0,
};

const ROW_INDENT_PX = 20;
const GUIDE_COLOR = "var(--fn-border-primary, #e8e8e8)";

function RootRow({
  agentId,
  entityCount,
}: {
  agentId: string;
  entityCount: number;
}) {
  const { t } = useTranslation();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        padding: "6px 4px",
        fontWeight: 600,
        color: "#262626",
      }}
    >
      <ChevronDown size={10} style={{ marginRight: 6, color: "#8c8c8c" }} />
      <span style={{ marginRight: 6 }}>🧠</span>
      <span>{agentId}</span>
      <Tag style={{ marginLeft: 8 }}>
        {t("memory.tree.entityCount", { n: entityCount })}
      </Tag>
    </div>
  );
}

function EntityRow({
  entity,
  expanded,
  onToggle,
  onViewSummary,
  onAdd,
}: {
  entity: EntityItem;
  expanded: boolean;
  onToggle: () => void;
  onViewSummary: () => void;
  onAdd: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const { t } = useTranslation();
  return (
    <div
      onClick={onToggle}
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 4,
        padding: "6px 4px 6px 0",
        marginLeft: ROW_INDENT_PX,
        cursor: "pointer",
        borderRadius: 4,
        position: "relative",
      }}
      className="memory-tree-row"
      onMouseEnter={(e) => {
        setHovered(true);
        (e.currentTarget as HTMLDivElement).style.background =
          "var(--fn-bg-hover, #fafafa)";
      }}
      onMouseLeave={(e) => {
        setHovered(false);
        (e.currentTarget as HTMLDivElement).style.background = "transparent";
      }}
    >
      {/* L-elbow guide */}
      <Guide />
      {expanded ? (
        <ChevronDown size={10} style={{ marginRight: 6, color: "#8c8c8c" }} />
      ) : (
        <ChevronRight size={10} style={{ marginRight: 6, color: "#8c8c8c" }} />
      )}
      <span style={{ marginRight: 6 }}>🏷️</span>
      <span style={{ fontWeight: 500 }}>{entity.canonical_name}</span>
      <Tag style={{ marginLeft: 8, fontSize: 11 }}>
        {entityTypeLabel(entity.entity_type, t)}
      </Tag>
      <Tag color="blue" style={{ fontSize: 11 }}>
        {t("memory.tree.atomCount", { n: entity.atom_count })}
      </Tag>
      {entity.aliases.length > 0 ? (
        <span
          style={{
            marginLeft: 6,
            fontSize: 11,
            color: "#bfbfbf",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: 220,
          }}
        >
          {t("memory.tree.aka", { names: entity.aliases.join(", ") })}
        </span>
      ) : null}
      {/* Push the summary affordance to the right edge. */}
      <span style={{ marginLeft: "auto" }} />
      {entity.page_dirty ? (
        <Tag color="orange" style={{ fontSize: 11, margin: 0 }}>
          {t("memory.tree.dirtyTag")}
        </Tag>
      ) : null}
      <Tooltip title={t("memory.create.addToTopicTip")}>
        <Button
          size="small"
          type="text"
          icon={<Plus size={13} />}
          onClick={(e) => {
            e.stopPropagation();
            onAdd();
          }}
          style={{
            flexShrink: 0,
            color: hovered ? "#1677ff" : "#8c8c8c",
          }}
        />
      </Tooltip>
      <Tooltip title={t("memory.tree.viewSummaryTip")}>
        <Button
          size="small"
          icon={<BookOpen size={13} />}
          onClick={(e) => {
            e.stopPropagation();
            onViewSummary();
          }}
          style={{
            flexShrink: 0,
            fontSize: 12,
            // Lift the button on row hover so it reads as the primary action.
            borderColor: hovered ? "#1677ff" : undefined,
            color: hovered ? "#1677ff" : undefined,
          }}
        >
          {t("memory.tree.viewSummary")}
        </Button>
      </Tooltip>
    </div>
  );
}

function AtomChildren({
  cache,
  onSelect,
  onEdit,
  onDeprecate,
}: {
  cache: { loading: boolean; items: AtomItem[] | null } | undefined;
  onSelect: (atom: AtomItem) => void;
  onEdit?: (atom: AtomItem) => void;
  onDeprecate?: (atom: AtomItem) => void;
}) {
  const { t } = useTranslation();
  if (!cache || cache.loading) {
    return (
      <div
        style={{
          marginLeft: ROW_INDENT_PX * 2,
          padding: "6px 4px",
          color: "#8c8c8c",
          fontSize: 12,
        }}
      >
        <Spin size="small" />{" "}
        <span style={{ marginLeft: 6 }}>{t("common.loading")}</span>
      </div>
    );
  }
  const atoms = cache.items ?? [];
  if (atoms.length === 0) {
    return (
      <div
        style={{
          marginLeft: ROW_INDENT_PX * 2,
          padding: "4px 4px 8px",
          color: "#bfbfbf",
          fontSize: 12,
          fontStyle: "italic",
        }}
      >
        {t("memory.tree.noAtomsInTopic")}
      </div>
    );
  }
  return (
    <ul style={listResetStyle}>
      {atoms.map((atom) => (
        <li key={atom.id}>
          <AtomRow
            atom={atom}
            onClick={() => onSelect(atom)}
            onEdit={onEdit}
            onDeprecate={onDeprecate}
          />
        </li>
      ))}
    </ul>
  );
}

function AtomRow({
  atom,
  onClick,
  onEdit,
  onDeprecate,
}: {
  atom: AtomItem;
  onClick: () => void;
  onEdit?: (atom: AtomItem) => void;
  onDeprecate?: (atom: AtomItem) => void;
}) {
  const [hovered, setHovered] = useState(false);
  const { t } = useTranslation();
  const showActions = hovered && !isAtomDeprecated(atom);

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        padding: "5px 4px",
        marginLeft: ROW_INDENT_PX * 2,
        cursor: "pointer",
        borderRadius: 4,
        position: "relative",
        gap: 6,
      }}
      onMouseEnter={(e) => {
        setHovered(true);
        (e.currentTarget as HTMLDivElement).style.background =
          "var(--fn-bg-hover, #fafafa)";
      }}
      onMouseLeave={(e) => {
        setHovered(false);
        (e.currentTarget as HTMLDivElement).style.background = "transparent";
      }}
    >
      <Guide />
      <ConfidenceDot value={atom.confidence} />
      <span style={{ marginRight: 4, fontSize: 12 }}>📌</span>
      <span
        style={{
          flex: 1,
          minWidth: 0,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          color: isAtomDeprecated(atom) ? "#bfbfbf" : "#262626",
          textDecoration: isAtomDeprecated(atom) ? "line-through" : "none",
        }}
      >
        {atom.assertion}
      </span>
      {atom.kind ? (
        <Tag style={{ fontSize: 10, lineHeight: "16px", margin: 0 }}>
          {kindLabel(atom.kind, t)}
        </Tag>
      ) : null}
      <span style={{ fontSize: 11, color: "#8c8c8c", whiteSpace: "nowrap" }}>
        {formatRelativeTime(atom.created_at, t)}
      </span>
      {showActions && onEdit ? (
        <Tooltip title={t("memory.edit.tooltip")}>
          <span
            onClick={(e) => {
              e.stopPropagation();
              onEdit(atom);
            }}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 22,
              height: 22,
              borderRadius: 4,
              color: "#1677ff",
              cursor: "pointer",
              flexShrink: 0,
            }}
          >
            <Pencil size={13} />
          </span>
        </Tooltip>
      ) : (
        <span style={{ width: 22, flexShrink: 0 }} />
      )}
      {showActions && onDeprecate ? (
        <Tooltip title={t("memory.tree.deprecateTooltip")}>
          <span
            onClick={(e) => {
              e.stopPropagation();
              onDeprecate(atom);
            }}
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 22,
              height: 22,
              borderRadius: 4,
              color: "#ff4d4f",
              cursor: "pointer",
              flexShrink: 0,
            }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLSpanElement).style.background =
                "#fff1f0")
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLSpanElement).style.background =
                "transparent")
            }
          >
            <Trash2 size={13} />
          </span>
        </Tooltip>
      ) : (
        <span style={{ width: 22, flexShrink: 0 }} />
      )}
    </div>
  );
}

function ConfidenceDot({ value }: { value: Confidence }) {
  const { t } = useTranslation();
  const color =
    value === "high" ? "#52c41a" : value === "medium" ? "#faad14" : "#f5222d";
  const tip =
    value === "high"
      ? t("memory.tree.confidenceHigh")
      : value === "medium"
      ? t("memory.tree.confidenceMedium")
      : t("memory.tree.confidenceLow");
  return (
    <span
      title={tip}
      aria-label={tip}
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
      }}
    />
  );
}

function Guide() {
  // simple vertical guide-line emulation: a 1px-wide bar at left of the row
  return (
    <span
      aria-hidden
      style={{
        position: "absolute",
        left: -ROW_INDENT_PX + 8,
        top: 0,
        bottom: 0,
        width: 1,
        background: GUIDE_COLOR,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Detail drawer
// ---------------------------------------------------------------------------

function AtomDetailDrawer({
  open,
  atom,
  agentId,
  onClose,
  onDeprecated,
  onReplaced,
}: {
  open: boolean;
  atom: AtomItem | null;
  agentId: string;
  onClose: () => void;
  onDeprecated: (atom: AtomItem) => void;
  onReplaced: (atom: AtomItem) => void;
}) {
  const { t } = useTranslation();
  return (
    <Drawer
      title={t("memory.atomDetail")}
      open={open}
      onClose={onClose}
      width={520}
    >
      {atom ? (
        <div>
          <Space size={4} wrap style={{ marginBottom: 12 }}>
            {atom.kind ? <Tag>{kindLabel(atom.kind, t)}</Tag> : null}
            <Tag>
              {t("memory.tree.importanceTag", {
                v: importanceLabel(atom.importance, t),
              })}
            </Tag>
            <Tag>
              {t("memory.tree.confidenceTag", {
                v: confidenceLabel(atom.confidence, t),
              })}
            </Tag>
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
          {(atom.search_terms ?? []).length > 0 ? (
            <>
              <Typography.Title level={5}>
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

          {/* Actions, shown only for active atoms */}
          {!isAtomDeprecated(atom) ? (
            <>
              <Typography.Title level={5} style={{ marginTop: 12 }}>
                {t("memory.tree.actions")}
              </Typography.Title>
              <Space>
                <Button
                  onClick={() =>
                    confirmEditAtom({
                      agentId,
                      atom,
                      onSuccess: onReplaced,
                    })
                  }
                >
                  {t("memory.edit.action")}
                </Button>
                <Button
                  danger
                  onClick={() =>
                    confirmDeprecateAtom({
                      agentId,
                      atom,
                      onSuccess: () => onDeprecated(atom),
                    })
                  }
                >
                  {t("memory.tree.deprecate")}
                </Button>
              </Space>
            </>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}

// ---------------------------------------------------------------------------
// Entity summary (L3 page) drawer
// ---------------------------------------------------------------------------

function EntitySummaryDrawer({
  agentId,
  entity,
  onClose,
}: {
  agentId: string;
  entity: EntityItem | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!entity) return;
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    setDetail(null);
    memoryDashboardApi
      .getEntity(agentId, entity.id)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, entity]);

  const page = detail?.page ?? null;

  return (
    <Drawer
      title={t("memory.entitySummary")}
      open={!!entity}
      onClose={onClose}
      width={560}
    >
      {entity ? (
        <div>
          <Space size={4} wrap style={{ marginBottom: 4 }}>
            <span style={{ fontSize: 16, fontWeight: 600 }}>🏷️</span>
            <span style={{ fontSize: 16, fontWeight: 600 }}>
              {entity.canonical_name}
            </span>
            <Tag>{entityTypeLabel(entity.entity_type, t)}</Tag>
            <Tag color="blue">
              {t("memory.tree.atomCount", { n: entity.atom_count })}
            </Tag>
            {page?.dirty ? (
              <Tag color="orange">{t("memory.tree.dirtyTag")}</Tag>
            ) : null}
          </Space>
          {entity.aliases.length > 0 ? (
            <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
              {t("memory.tree.akaInline", {
                names: entity.aliases.join("、"),
              })}
            </Typography.Paragraph>
          ) : null}

          <EntitySummaryBody loading={loading} failed={failed} page={page} />
        </div>
      ) : null}
    </Drawer>
  );
}

function EntitySummaryBody({
  loading,
  failed,
  page,
}: {
  loading: boolean;
  failed: boolean;
  page: EntityPage | null;
}) {
  const { t } = useTranslation();
  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />;
  if (failed) {
    return (
      <Typography.Paragraph type="danger">
        {t("memory.tree.summaryLoadFailed")}
      </Typography.Paragraph>
    );
  }
  if (!page || !page.summary_markdown.trim()) {
    return (
      <div style={{ marginTop: 12 }}>
        <Typography.Paragraph type="secondary">
          {t("memory.tree.summaryNotGenerated")}
        </Typography.Paragraph>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          {t("memory.tree.summaryNotGeneratedDesc")}
        </Typography.Paragraph>
      </div>
    );
  }
  return (
    <>
      {page.headline ? (
        <Typography.Paragraph
          style={{
            fontSize: 13,
            color: "#595959",
            background: "var(--fn-bg-hover, #fafafa)",
            borderRadius: 6,
            padding: "8px 12px",
          }}
        >
          {page.headline}
        </Typography.Paragraph>
      ) : null}
      <div style={{ marginTop: 4 }}>
        <Markdown content={page.summary_markdown} />
      </div>
      <Typography.Paragraph
        type="secondary"
        style={{ fontSize: 12, marginTop: 16 }}
      >
        {t("memory.tree.summaryVersion", {
          v: page.summary_version,
          time: formatRelativeTime(page.updated_at, t),
        })}
        {page.dirty ? t("memory.tree.summaryDirtyNote") : ""}
      </Typography.Paragraph>
    </>
  );
}

// ---------------------------------------------------------------------------
// Helpers
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

function entityTypeLabel(type: string, t: TFunction): string {
  switch ((type || "").toLowerCase()) {
    case "person":
      return t("memory.entityType.person");
    case "place":
      return t("memory.entityType.place");
    case "project":
      return t("memory.entityType.project");
    case "tool":
      return t("memory.entityType.tool");
    case "concept":
      return t("memory.entityType.concept");
    case "organization":
      return t("memory.entityType.organization");
    case "event":
      return t("memory.entityType.event");
    default:
      return type || t("memory.entityType.other");
  }
}

function importanceLabel(v: string, t: TFunction): string {
  return v === "high"
    ? t("memory.tree.importanceHigh")
    : v === "medium"
    ? t("memory.tree.importanceMedium")
    : t("memory.tree.importanceLow");
}

function confidenceLabel(v: string, t: TFunction): string {
  return v === "high"
    ? t("memory.tree.confidenceHigh")
    : v === "medium"
    ? t("memory.tree.confidenceMedium")
    : t("memory.tree.confidenceLow");
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
