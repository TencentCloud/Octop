import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
  type WheelEvent,
} from "react";
import {
  Alert,
  App,
  Button,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Spin,
  Tag,
  Typography,
} from "antd";
import { RefreshCw, Search, Trash2, Waypoints } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";

import {
  knowledgeBasesApi,
  type KnowledgeGraph,
  type KnowledgeGraphEntityDetail,
} from "../../api/modules/knowledgeBases";
import { apiErrorMessage } from "../../utils/apiError";
import { layoutGraph, neighborIds } from "./knowledgeGraphLayout";
import styles from "./KnowledgeGraphModal.module.less";

const CANVAS_WIDTH = 760;
const CANVAS_HEIGHT = 520;
const NODE_LIMIT = 80;
const POLL_MS = 3000;
/** Above this many nodes only the well-connected ones keep a permanent label. */
const LABEL_ALL_LIMIT = 40;

const ENTITY_TYPES = [
  "person",
  "organization",
  "location",
  "product",
  "technology",
  "event",
  "document",
  "concept",
  "time",
  "other",
] as const;

function typeClass(type: string): string {
  const known = (ENTITY_TYPES as readonly string[]).includes(type)
    ? type
    : "other";
  return styles[`type_${known}`];
}

interface Props {
  open: boolean;
  kbId: string | null;
  kbName: string;
  /** The viewer may build and delete this knowledge base's graph. */
  canWrite: boolean;
  /** An extraction model is configured, so a build can start. */
  canBuild: boolean;
  onClose: () => void;
}

export default function KnowledgeGraphModal({
  open,
  kbId,
  kbName,
  canWrite,
  canBuild,
  onClose,
}: Props) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KnowledgeGraphEntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const requestSeq = useRef(0);

  const load = useCallback(
    async (quiet = false) => {
      if (!kbId) return;
      const seq = (requestSeq.current += 1);
      if (!quiet) setLoading(true);
      try {
        const next = await knowledgeBasesApi.getGraph(kbId, {
          q: search || undefined,
          limit: NODE_LIMIT,
        });
        if (seq === requestSeq.current) setGraph(next);
      } catch (error) {
        if (!quiet) {
          message.error(
            apiErrorMessage(error, t("knowledgeBases.graphLoadFailed"), t),
          );
        }
      } finally {
        if (!quiet && seq === requestSeq.current) setLoading(false);
      }
    },
    [kbId, message, search, t],
  );

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  useEffect(() => {
    if (open) return;
    setGraph(null);
    setSearchDraft("");
    setSearch("");
    setSelectedId(null);
    setDetail(null);
    setView({ x: 0, y: 0, scale: 1 });
  }, [open]);

  const pending = graph?.stats.documents_pending ?? 0;
  useEffect(() => {
    // Without an extraction model nothing is running, so there is nothing to wait for.
    if (!open || pending <= 0 || !canBuild) return;
    const timer = window.setInterval(() => void load(true), POLL_MS);
    return () => window.clearInterval(timer);
  }, [open, pending, canBuild, load]);

  useEffect(() => {
    if (!open || !kbId || !selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    knowledgeBasesApi
      .getGraphEntity(kbId, selectedId)
      .then((next) => {
        if (!cancelled) setDetail(next);
      })
      .catch((error) => {
        if (cancelled) return;
        setDetail(null);
        message.error(
          apiErrorMessage(error, t("knowledgeBases.graphLoadFailed"), t),
        );
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, kbId, selectedId, message, t]);

  const nodes = useMemo(() => graph?.nodes ?? [], [graph]);
  const edges = useMemo(() => graph?.edges ?? [], [graph]);
  // Only the set of nodes and edges decides the layout; polling must not reshuffle it.
  const layoutKey = useMemo(
    () =>
      `${nodes.map((node) => node.id).join("|")}#${edges
        .map((edge) => `${edge.source}>${edge.target}`)
        .join("|")}`,
    [nodes, edges],
  );
  const positions = useMemo(
    () =>
      layoutGraph(nodes, edges, {
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        margin: 56,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [layoutKey],
  );
  const maxMentions = useMemo(
    () => Math.max(1, ...nodes.map((node) => node.mentions)),
    [nodes],
  );
  // A selected entity that the current search filtered out must not dim what is shown.
  const focusId =
    hoveredId ?? (selectedId && positions.has(selectedId) ? selectedId : null);
  const focusNeighbors = useMemo(
    () => (focusId ? neighborIds(focusId, edges) : new Set<string>()),
    [focusId, edges],
  );
  const labelDegree = useMemo(() => {
    if (nodes.length <= LABEL_ALL_LIMIT) return 0;
    const degrees = nodes.map((node) => node.degree).sort((a, b) => b - a);
    return Math.max(degrees[LABEL_ALL_LIMIT - 1] ?? 0, 1);
  }, [nodes]);
  const typesPresent = useMemo(
    () =>
      ENTITY_TYPES.filter((type) =>
        nodes.some((node) => (node.type || "other") === type),
      ),
    [nodes],
  );

  const build = async () => {
    if (!kbId) return;
    setBuilding(true);
    try {
      const result = await knowledgeBasesApi.buildGraph(kbId);
      message.success(
        t("knowledgeBases.graphBuildQueued", { count: result.enqueued }),
      );
      await load(true);
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.graphBuildFailed"), t),
      );
    } finally {
      setBuilding(false);
    }
  };

  const remove = async () => {
    if (!kbId) return;
    try {
      await knowledgeBasesApi.deleteGraph(kbId);
      setSelectedId(null);
      message.success(t("knowledgeBases.graphDeleted"));
      await load(true);
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.graphDeleteFailed"), t),
      );
    }
  };

  const onWheel = (event: WheelEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const pointX = ((event.clientX - box.left) / box.width) * CANVAS_WIDTH;
    const pointY = ((event.clientY - box.top) / box.height) * CANVAS_HEIGHT;
    setView((current) => {
      const scale = Math.min(
        Math.max(current.scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15), 0.5),
        4,
      );
      const ratio = scale / current.scale;
      // Keep the point under the cursor where it is while zooming.
      return {
        scale,
        x: pointX - (pointX - current.x) * ratio,
        y: pointY - (pointY - current.y) * ratio,
      };
    });
  };

  const onPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if ((event.target as Element).closest("[data-node]")) return;
    drag.current = { x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const start = drag.current;
    if (!start) return;
    const box = event.currentTarget.getBoundingClientRect();
    const moveX = ((event.clientX - start.x) / box.width) * CANVAS_WIDTH;
    const moveY = ((event.clientY - start.y) / box.height) * CANVAS_HEIGHT;
    drag.current = { x: event.clientX, y: event.clientY };
    setView((current) => ({
      ...current,
      x: current.x + moveX,
      y: current.y + moveY,
    }));
  };

  const onPointerUp = () => {
    drag.current = null;
  };

  const stats = graph?.stats;
  const built = Boolean(stats?.built);

  const renderCanvas = () => {
    if (!graph || !stats) return null;
    if (!built) {
      return (
        <div className={styles.placeholder}>
          <Empty
            image={<Waypoints size={40} strokeWidth={1.5} />}
            description={
              <>
                <div className={styles.placeholderTitle}>
                  {t("knowledgeBases.graphNotBuilt")}
                </div>
                <div className={styles.placeholderHint}>
                  {t(
                    canWrite
                      ? canBuild
                        ? "knowledgeBases.graphNotBuiltHint"
                        : "knowledgeBases.graphNeedsModel"
                      : "knowledgeBases.graphNotBuiltReader",
                  )}
                </div>
              </>
            }
          >
            {canWrite && canBuild ? (
              <Button
                type="primary"
                loading={building}
                disabled={stats.documents_total === 0}
                onClick={() => void build()}
              >
                {t("knowledgeBases.graphBuild")}
              </Button>
            ) : null}
          </Empty>
        </div>
      );
    }
    if (nodes.length === 0) {
      return (
        <div className={styles.placeholder}>
          <Empty
            description={t(
              search
                ? "knowledgeBases.graphNoMatch"
                : pending > 0
                ? "knowledgeBases.graphBuilding"
                : "knowledgeBases.graphEmpty",
            )}
          />
        </div>
      );
    }
    return (
      <svg
        className={styles.canvas}
        viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
        role="img"
        aria-label={t("knowledgeBases.graphTitle", { name: kbName })}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
          {edges.map((edge) => {
            const from = positions.get(edge.source);
            const to = positions.get(edge.target);
            if (!from || !to) return null;
            const active =
              focusId !== null &&
              (edge.source === focusId || edge.target === focusId);
            return (
              <g key={`${edge.source}>${edge.target}`}>
                <line
                  className={cx(
                    styles.edge,
                    active && styles.edgeActive,
                    focusId && !active && styles.dimmed,
                  )}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  strokeWidth={Math.min(1 + edge.weight / 12, 4) / view.scale}
                />
              </g>
            );
          })}
          {nodes.map((node) => {
            const point = positions.get(node.id);
            if (!point) return null;
            const radius =
              (6 + 10 * Math.sqrt(node.mentions / maxMentions)) / view.scale;
            const focused = node.id === focusId;
            const related = focusNeighbors.has(node.id);
            const labelled =
              focused ||
              related ||
              node.id === selectedId ||
              (focusId === null && node.degree >= labelDegree);
            return (
              <g
                key={node.id}
                data-node
                className={cx(
                  styles.node,
                  focusId && !focused && !related && styles.dimmed,
                )}
                tabIndex={0}
                role="button"
                aria-label={node.name}
                aria-pressed={node.id === selectedId}
                onClick={() => setSelectedId(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelectedId(node.id);
                  }
                }}
                onPointerEnter={() => setHoveredId(node.id)}
                onPointerLeave={() => setHoveredId(null)}
              >
                <circle
                  className={cx(
                    styles.nodeDot,
                    typeClass(node.type),
                    node.id === selectedId && styles.nodeSelected,
                  )}
                  cx={point.x}
                  cy={point.y}
                  r={radius}
                  strokeWidth={(node.id === selectedId ? 3 : 1.5) / view.scale}
                />
                {labelled ? (
                  <text
                    className={styles.nodeLabel}
                    x={point.x}
                    y={point.y + radius + 12 / view.scale}
                    fontSize={12 / view.scale}
                    textAnchor="middle"
                  >
                    {node.name.length > 18
                      ? `${node.name.slice(0, 17)}…`
                      : node.name}
                  </text>
                ) : null}
              </g>
            );
          })}
          {/* Drawn last so relation names stay readable over node labels. */}
          {focusId
            ? edges.map((edge) => {
                const from = positions.get(edge.source);
                const to = positions.get(edge.target);
                if (
                  !from ||
                  !to ||
                  (edge.source !== focusId && edge.target !== focusId)
                ) {
                  return null;
                }
                return (
                  <text
                    key={`${edge.source}>${edge.target}`}
                    className={styles.edgeLabel}
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 4 / view.scale}
                    fontSize={11 / view.scale}
                    textAnchor="middle"
                  >
                    {edge.labels.join(" / ")}
                  </text>
                );
              })
            : null}
        </g>
      </svg>
    );
  };

  const renderDetail = () => {
    if (!selectedId) {
      return (
        <Typography.Text type="secondary" className={styles.detailHint}>
          {t("knowledgeBases.graphSelectHint")}
        </Typography.Text>
      );
    }
    if (detailLoading && !detail) return <Spin />;
    if (!detail) return null;
    return (
      <Spin spinning={detailLoading}>
        <div className={styles.detailHeader}>
          <span className={styles.detailName}>{detail.entity.name}</span>
          <Tag className={styles.detailType}>
            <span
              className={cx(styles.legendDot, typeClass(detail.entity.type))}
            />
            {t(`knowledgeBases.graphType.${detail.entity.type || "other"}`, {
              defaultValue: detail.entity.type,
            })}
          </Tag>
        </div>
        {detail.entity.description ? (
          <p className={styles.detailDescription}>
            {detail.entity.description}
          </p>
        ) : null}
        <div className={styles.detailSection}>
          {t("knowledgeBases.graphRelations", {
            count: detail.relations.length,
          })}
        </div>
        {detail.relations.length === 0 ? (
          <Typography.Text type="secondary">
            {t("knowledgeBases.graphNoRelations")}
          </Typography.Text>
        ) : (
          <ul className={styles.relationList}>
            {detail.relations.map((relation) => {
              const outgoing = relation.source.id === detail.entity.id;
              const other = outgoing ? relation.target : relation.source;
              return (
                <li
                  key={`${relation.source.id}>${relation.target.id}>${relation.label}`}
                  className={styles.relationItem}
                >
                  <div className={styles.relationLine}>
                    <span className={styles.relationArrow} aria-hidden>
                      {outgoing ? "→" : "←"}
                    </span>
                    <span className={styles.relationLabel}>
                      {relation.label}
                    </span>
                    <button
                      type="button"
                      className={styles.relationOther}
                      onClick={() => setSelectedId(other.id)}
                    >
                      {other.name}
                    </button>
                  </div>
                  {relation.description ? (
                    <div className={styles.relationDescription}>
                      {relation.description}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        <div className={styles.detailSection}>
          {t("knowledgeBases.graphPassages", {
            count: detail.passages.length,
          })}
        </div>
        <ul className={styles.passageList}>
          {detail.passages.map((passage) => (
            <li
              key={`${passage.doc_id}:${passage.ordinal}`}
              className={styles.passageItem}
            >
              <div className={styles.passageSource}>
                {passage.filename} ·{" "}
                {t("knowledgeBases.chunkLabel", { n: passage.ordinal + 1 })}
              </div>
              <div className={styles.passageText}>{passage.text}</div>
            </li>
          ))}
        </ul>
      </Spin>
    );
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={1160}
      destroyOnHidden
      title={t("knowledgeBases.graphTitle", { name: kbName })}
    >
      <div className={styles.toolbar}>
        <div className={styles.stats}>
          {stats && built ? (
            <>
              <Tag>
                {t("knowledgeBases.graphEntities", { count: stats.entities })}
              </Tag>
              <Tag>
                {t("knowledgeBases.graphRelationsTotal", {
                  count: stats.relations,
                })}
              </Tag>
              <Tag color={pending > 0 ? "processing" : undefined}>
                {t("knowledgeBases.graphDocuments", {
                  ready: stats.documents_ready,
                  total: stats.documents_total,
                })}
              </Tag>
              {stats.documents_failed > 0 ? (
                <Tag color="error">
                  {t("knowledgeBases.graphDocumentsFailed", {
                    count: stats.documents_failed,
                  })}
                </Tag>
              ) : null}
            </>
          ) : null}
        </div>
        {built ? (
          <div className={styles.actions}>
            <Input
              className={styles.search}
              allowClear
              prefix={<Search size={14} />}
              placeholder={t("knowledgeBases.graphSearch")}
              value={searchDraft}
              onChange={(event) => {
                setSearchDraft(event.target.value);
                if (!event.target.value) setSearch("");
              }}
              onPressEnter={() => setSearch(searchDraft.trim())}
            />
            {canWrite ? (
              <Button
                icon={<RefreshCw size={14} />}
                loading={building}
                disabled={!canBuild}
                title={
                  canBuild ? undefined : t("knowledgeBases.graphNeedsModel")
                }
                onClick={() => void build()}
              >
                {t("knowledgeBases.graphRebuild")}
              </Button>
            ) : null}
            {canWrite ? (
              <Popconfirm
                title={t("knowledgeBases.graphDeleteConfirm")}
                okText={t("common.confirm")}
                cancelText={t("common.cancel")}
                onConfirm={() => void remove()}
              >
                <Button
                  danger
                  icon={<Trash2 size={14} />}
                  aria-label={t("knowledgeBases.graphDelete")}
                  title={t("knowledgeBases.graphDelete")}
                />
              </Popconfirm>
            ) : null}
          </div>
        ) : null}
      </div>
      {stats && built && pending > 0 ? (
        <Alert
          className={styles.notice}
          type={canBuild ? "info" : "warning"}
          showIcon
          message={t(
            canBuild
              ? "knowledgeBases.graphBuildingNotice"
              : "knowledgeBases.graphWaitingNotice",
            { count: pending },
          )}
        />
      ) : null}
      {stats && built && pending === 0 && stats.documents_partial > 0 ? (
        <Alert
          className={styles.notice}
          type="warning"
          showIcon
          message={t("knowledgeBases.graphPartialNotice", {
            count: stats.documents_partial,
          })}
        />
      ) : null}
      <Spin spinning={loading}>
        <div className={styles.body}>
          <div className={styles.canvasPane}>
            {renderCanvas()}
            {built && nodes.length > 0 ? (
              <div className={styles.legend}>
                {typesPresent.map((type) => (
                  <span key={type} className={styles.legendItem}>
                    <span className={cx(styles.legendDot, typeClass(type))} />
                    {t(`knowledgeBases.graphType.${type}`)}
                  </span>
                ))}
                {stats && stats.entities > nodes.length && !search ? (
                  <span className={styles.legendNote}>
                    {t("knowledgeBases.graphTopNote", {
                      shown: nodes.length,
                      total: stats.entities,
                    })}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
          {built ? (
            <aside className={styles.detailPane}>{renderDetail()}</aside>
          ) : null}
        </div>
      </Spin>
    </Modal>
  );
}
