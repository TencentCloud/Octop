/**
 * `ArtifactPanel` — the 11 required artifacts: what exists, who may overwrite it, and
 * **which index fields have no writer yet**.
 *
 * ★ The honest-rendering rule (T-20 acceptance ②): `ArtifactItemOut.phase` / `version`
 * / `hash` / `created_at` are **`null` today** — the columns exist and are mapped, but
 * nothing materialises `kind='workflow'` rows until **T-45**. A `null` there means
 * **"待写入方"** (no writer yet), which is a *different fact* from "—" (not applicable)
 * and from a fabricated value. We render the difference, so a later reader cannot
 * mistake "not indexed" for "indexed and empty".
 *
 * `owners: string[] | null` carries the ownership table: `[]` is a **real** value —
 * "runtime only, no role may overwrite" — and must not be collapsed into "no owner".
 *
 * Presentational (AGENTS.md §5): no fetching — the caller owns the request.
 */

import { Empty, Table, Tag, Tooltip, Typography } from "antd";
import { useTranslation } from "react-i18next";

import type { ArtifactItemWire } from "../../../api/modules/teamRuns";

/** Index fields whose writer does not exist yet (T-45) — rendered as 待写入方 when null. */
export const PENDING_WRITER_FIELDS = [
  "phase",
  "version",
  "hash",
  "created_at",
] as const;
export type PendingWriterField = (typeof PENDING_WRITER_FIELDS)[number];

export type IndexFieldValue = string | number | null;

/**
 * `null` ⇒ **待写入方**（无写入方），not "—" and not a zero/empty stand-in.
 * A non-null value is returned as-is (falsy-but-real values such as `0` stay visible —
 * `0` is a measurement, absence is not).
 */
export function indexFieldDisplay(
  value: IndexFieldValue,
  t: (key: string) => string,
): { text: string; pending: boolean } {
  if (value === null || value === undefined) {
    return { text: t("teamRuns.artifacts.awaitingWriter"), pending: true };
  }
  return { text: String(value), pending: false };
}

/** `owners` semantics: `null` = unrestricted (not in the table), `[]` = runtime only. */
export function ownersLabel(
  owners: string[] | null | undefined,
  t: (key: string) => string,
): { text: string; runtimeOnly: boolean } {
  if (owners === null || owners === undefined) {
    return { text: t("teamRuns.artifacts.unrestricted"), runtimeOnly: false };
  }
  if (owners.length === 0) {
    return { text: t("teamRuns.artifacts.runtimeOnly"), runtimeOnly: true };
  }
  return { text: owners.join(" / "), runtimeOnly: false };
}

export interface ArtifactPanelProps {
  items: ArtifactItemWire[];
  loading?: boolean;
}

export default function ArtifactPanel({ items, loading }: ArtifactPanelProps) {
  const { t } = useTranslation();
  if (!items.length) {
    return (
      <Empty
        data-testid="artifacts-empty"
        description={
          loading
            ? t("teamRuns.artifacts.loading")
            : t("teamRuns.artifacts.none")
        }
      />
    );
  }
  return (
    <Table<ArtifactItemWire>
      data-testid="artifact-panel"
      rowKey="name"
      size="small"
      pagination={false}
      dataSource={items}
      columns={[
        {
          title: t("teamRuns.artifacts.name"),
          dataIndex: "name",
          render: (name: string, row) => (
            <span>
              {name}
              {row.present ? null : (
                <Tag className="ml-1" data-testid={`artifact-absent-${name}`}>
                  {t("teamRuns.artifacts.absent")}
                </Tag>
              )}
            </span>
          ),
        },
        {
          title: t("teamRuns.artifacts.owners"),
          dataIndex: "owners",
          render: (_: unknown, row) => {
            const label = ownersLabel(row.owners, t);
            return label.runtimeOnly ? (
              <Tooltip title={t("teamRuns.artifacts.runtimeOnlyHint")}>
                <Tag color="blue" data-testid={`artifact-owners-${row.name}`}>
                  {label.text}
                </Tag>
              </Tooltip>
            ) : (
              <span data-testid={`artifact-owners-${row.name}`}>
                {label.text}
              </span>
            );
          },
        },
        ...PENDING_WRITER_FIELDS.map((field) => ({
          title: t(`teamRuns.artifacts.field.${field}`),
          dataIndex: field,
          render: (value: IndexFieldValue, row: ArtifactItemWire) => {
            const display = indexFieldDisplay(value, t);
            return display.pending ? (
              <Typography.Text
                type="secondary"
                data-testid={`artifact-pending-${row.name}-${field}`}
              >
                {display.text}
              </Typography.Text>
            ) : (
              <span data-testid={`artifact-value-${row.name}-${field}`}>
                {display.text}
              </span>
            );
          },
        })),
      ]}
    />
  );
}
