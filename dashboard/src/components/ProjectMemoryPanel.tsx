/**
 * Read-only "memory scope" panel — renders one agent's memory grouped by
 * namespace layer (``project`` → ``team`` → ``agent``).
 *
 * Shared building block (``AGENTS.md`` §5): it is **presentational** — it never
 * fetches, never writes, and does not import from ``pages/``. Callers own the
 * request and pass the resulting groups down; the prop types below are
 * structural, so a caller's richer wire type is assignable without a cast.
 *
 * Mount sites (T-38 acceptance, **lead ruling (a)**): delivered count is **≥1 —
 * the 作用域切换器** on the agent Memory page (via ``ScopedMemoryView``). The
 * other half of the original criterion, 「项目详情页 Tab」, belongs to **T-40** and
 * is **deferred**: its landing zone (``pages/Projects/Detail/`` +
 * ``api/modules/projects.ts``) is another workstream's active battlefield, so
 * landing it now would only create same-file merge conflicts. That deferral is
 * precisely why this component stays presentational and fetch-free — T-40 mounts
 * it directly, with no change here.
 *
 * Why one component for three layers: the four visibility facts users need are
 * the same on every surface —
 *
 * * rows exist            → render them, each tagged with the layer it came from;
 * * no rows               → an **empty state**, not an error (a project with no
 *                           memory yet is a normal starting point, T-37);
 * * no access (HTTP 403)  → a **permission state**, never a page crash (the
 *                           project gate is checked on every path, SPEC §11.3);
 * * the row is agent-only → say so ("not in the project layer yet" — R19).
 *
 * Read-only **by default**: with no ``onRecordToProject`` prop this component has
 * no write affordance at all — that is the T-38 contract, and the 作用域切换器 call
 * site still passes nothing, so it is unchanged. T-41 adds the write half as
 * **optional** props: the panel only ever invokes the caller's callback, and
 * whether the caller may write at all stays the caller's decision — never derived
 * from "this row was readable" (SPEC B38: 读按 ``project_members``、写按团队 owner /
 * 项目角色，**两者不合并**).
 */

import { Alert, Button, Empty, Spin, Tag, Typography } from "antd";
import { FolderKanban, Lock, Users, User } from "lucide-react";
import { useTranslation } from "react-i18next";

const { Text } = Typography;

/** Minimal structural view of one memory row (assignable from the wire type). */
export interface ScopePanelItem {
  id: string;
  text: string;
  source_layer: string;
  namespace: string;
  created_at?: string | null;
  importance?: string | null;
}

/** Minimal structural view of one namespace layer. */
export interface ScopePanelGroup {
  source_layer: string;
  namespace: string;
  total: number;
  items: ScopePanelItem[];
}

export interface ProjectMemoryPanelProps {
  groups: ScopePanelGroup[];
  /** Layer the switcher focuses on; rendered first and highlighted. */
  scope?: string;
  loading?: boolean;
  /** The project layer was refused (HTTP 403) — a permission state, not an error. */
  denied?: boolean;
  /** Any non-permission failure, already turned into display text by the caller. */
  error?: string | null;
  onRetry?: () => void;
  /**
   * T-41 (write half): render a per-row 「记到项目」 affordance for rows that live
   * **only** in the agent's private layer. **Omit it and the panel stays
   * read-only** — which is what the T-38 call site does, so the read-visibility
   * contract is unchanged by default.
   *
   * The panel still never writes: it only invokes this callback. The caller owns
   * the request, including the decision that the user may write at all (SPEC B38
   * — being able to *read* project memory must not imply being able to write it).
   */
  onRecordToProject?: (item: ScopePanelItem) => void;
  /**
   * Why the write affordance is unavailable (e.g. read-only role, or the write
   * surface is not wired yet). Shown **in place of** the action rather than
   * hiding it, so "I can read this but not move it" is stated, not implied.
   */
  recordToProjectHint?: string | null;
}

/** Layer metadata in the backend's dedup order (project wins a duplicate). */
const LAYER_META: Record<
  string,
  { labelKey: string; fallback: string; icon: typeof User }
> = {
  project: {
    labelKey: "memory.scope.layerProject",
    fallback: "项目层",
    icon: FolderKanban,
  },
  team: { labelKey: "memory.scope.layerTeam", fallback: "团队层", icon: Users },
  agent: {
    labelKey: "memory.scope.layerAgent",
    fallback: "agent 私有层",
    icon: User,
  },
};

const LAYER_ORDER = ["project", "team", "agent"] as const;

export default function ProjectMemoryPanel({
  groups,
  scope,
  loading = false,
  denied = false,
  error = null,
  onRetry,
  onRecordToProject,
  recordToProjectHint = null,
}: ProjectMemoryPanelProps) {
  const { t } = useTranslation();

  // The project gate runs before any read, so "denied" outranks both loading and
  // content: showing rows we were not allowed to fetch would be the worst bug.
  if (denied) {
    return (
      <Empty
        data-testid="memory-scope-denied"
        image={<Lock size={40} strokeWidth={1.5} />}
        description={
          <span>
            {t("memory.scope.noAccess", "无权查看该项目的记忆")}
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t(
                "memory.scope.noAccessHint",
                "项目记忆按项目成员授权；请让项目 owner 把你加为成员。",
              )}
            </Text>
          </span>
        }
        style={{ marginTop: 48 }}
      />
    );
  }

  if (loading) {
    return (
      <div
        data-testid="memory-scope-loading"
        style={{ textAlign: "center", padding: "48px 0" }}
      >
        <Spin />
      </div>
    );
  }

  if (error != null) {
    return (
      <Alert
        data-testid="memory-scope-error"
        type="error"
        showIcon
        message={t("memory.scope.loadFailed", "记忆加载失败")}
        description={error || undefined}
        style={{ marginTop: 16 }}
        action={
          onRetry ? (
            <Button size="small" onClick={onRetry}>
              {t("memory.scope.retry", "重试")}
            </Button>
          ) : null
        }
      />
    );
  }

  const known = LAYER_ORDER.filter((layer) =>
    groups.some((g) => g.source_layer === layer),
  );
  const extra = groups
    .map((g) => g.source_layer)
    .filter((layer) => !(LAYER_ORDER as readonly string[]).includes(layer));
  const ordered: string[] = [...known, ...Array.from(new Set(extra))];
  const totalItems = groups.reduce((n, g) => n + g.items.length, 0);

  // Criterion ③: a project with no memory yet is an empty state, not an error.
  if (ordered.length === 0 || totalItems === 0) {
    return (
      <Empty
        data-testid="memory-scope-empty"
        description={
          <span>
            {t("memory.scope.empty", "这一层还没有记忆")}
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t(
                "memory.scope.emptyHint",
                "空是正常起点：写入要在后续步骤里发生，本页只做只读浏览。",
              )}
            </Text>
          </span>
        }
        style={{ marginTop: 48 }}
      />
    );
  }

  return (
    <div data-testid="memory-scope-panel">
      {ordered.map((layer) => {
        const group = groups.find((g) => g.source_layer === layer);
        if (!group || group.items.length === 0) return null;
        const meta = LAYER_META[layer] ?? {
          labelKey: "",
          fallback: layer,
          icon: User,
        };
        const Icon = meta.icon;
        const isFocused = scope === layer;
        return (
          <section
            key={layer}
            data-testid={`memory-scope-group-${layer}`}
            style={{
              marginBottom: 20,
              outline: isFocused
                ? "1px solid var(--octop-border, #d9d9d9)"
                : "none",
              borderRadius: 8,
              padding: isFocused ? 12 : 0,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 8,
                flexWrap: "wrap",
              }}
            >
              <Icon size={16} strokeWidth={1.8} />
              <Text strong>
                {meta.labelKey
                  ? t(meta.labelKey, meta.fallback)
                  : meta.fallback}
              </Text>
              <Tag
                color={
                  layer === "project"
                    ? "blue"
                    : layer === "team"
                    ? "purple"
                    : "default"
                }
              >
                {group.namespace}
              </Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t("memory.scope.itemCount", "{{count}} 条", {
                  count: group.items.length,
                })}
              </Text>
            </div>

            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
              {group.items.map((item) => (
                <li
                  key={`${layer}:${item.id}`}
                  data-testid="memory-scope-item"
                  data-layer={layer}
                  style={{
                    padding: "8px 10px",
                    borderBottom: "1px solid var(--octop-border, #f0f0f0)",
                  }}
                >
                  <div
                    style={{ display: "flex", gap: 8, alignItems: "baseline" }}
                  >
                    <Tag
                      data-testid={`memory-scope-tag-${layer}`}
                      style={{ flex: "0 0 auto" }}
                    >
                      {meta.labelKey
                        ? t(meta.labelKey, meta.fallback)
                        : meta.fallback}
                    </Tag>
                    <span style={{ flex: 1, wordBreak: "break-word" }}>
                      {item.text}
                    </span>
                  </div>
                  {/*
                    Criterion ④ / R19: the backend dedupes in project → team →
                    agent order, so a row reported under `agent` is by
                    construction one that exists *only* in the agent's private
                    namespace. Say that out loud instead of leaving the user to
                    infer it from the tag.
                  */}
                  {layer === "agent" ? (
                    <Text
                      type="secondary"
                      data-testid="memory-scope-agent-only"
                      style={{ fontSize: 12, marginLeft: 4 }}
                    >
                      {t(
                        "memory.scope.agentOnly",
                        "仅 agent 私有层 · 尚未进入团队 / 项目层",
                      )}
                    </Text>
                  ) : null}
                  {/*
                    T-41 (write half). Rows reported under `agent` are exactly the
                    ones that exist only in the private layer (see the note above),
                    so they are the only sensible 「记到项目」 targets.
                    `onRecordToProject` omitted ⇒ this renders nothing at all, which
                    is how the T-38 host stays read-only.
                  */}
                  {layer === "agent" &&
                  (onRecordToProject || recordToProjectHint) ? (
                    <div
                      data-testid="memory-scope-write"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginLeft: 4,
                        marginTop: 4,
                        flexWrap: "wrap",
                      }}
                    >
                      {onRecordToProject ? (
                        <Button
                          size="small"
                          data-testid="memory-scope-record-to-project"
                          onClick={() => onRecordToProject(item)}
                        >
                          {t("memory.scope.recordToProject", "记到项目")}
                        </Button>
                      ) : null}
                      {recordToProjectHint ? (
                        <Text
                          type="secondary"
                          data-testid="memory-scope-write-hint"
                          style={{ fontSize: 12 }}
                        >
                          {recordToProjectHint}
                        </Text>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
