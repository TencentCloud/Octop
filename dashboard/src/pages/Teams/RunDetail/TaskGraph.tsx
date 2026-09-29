/**
 * `TaskGraph` — the run's task board: nodes, dependency edges, and read-side violations.
 *
 * Two facts the panel must not lose:
 *
 * * **`edges`** come from `dependsOn` (`{ from, to }`); a node whose dependency is not on
 *   the board yet is drawn with the edge still present — the board is what the DB says,
 *   not a cleaned-up view.
 * * **`violations`** are the read-side report (`check_run()` never blocks). A board with
 *   zero violations and a board with violations look different; an empty board says
 *   "no tasks registered", never "all good".
 *
 * Presentational (AGENTS.md §5): no fetching — the caller owns the request.
 */

import { Alert, Empty, Table, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";

import type {
  TaskBoardWire,
  TaskNodeWire,
  ViolationWire,
} from "../../../api/modules/teamRuns";

export interface TaskGraphProps {
  board: TaskBoardWire | null;
  loading?: boolean;
}

export default function TaskGraph({ board, loading }: TaskGraphProps) {
  const { t } = useTranslation();
  if (!board) {
    return (
      <Empty
        data-testid="tasks-not-loaded"
        description={
          loading ? t("teamRuns.tasks.loading") : t("teamRuns.tasks.notLoaded")
        }
      />
    );
  }
  const { nodes, edges, violations } = board;
  return (
    <div data-testid="task-graph" className="flex flex-col gap-3">
      {violations.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          data-testid="task-violations"
          message={t("teamRuns.tasks.violations", { count: violations.length })}
          description={
            <ul className="m-0 pl-4">
              {violations.map((item: ViolationWire, index: number) => (
                <li key={`${item.code}-${item.task_id ?? index}`}>
                  <code>{item.code}</code>
                  {item.task_id ? ` · ${item.task_id}` : ""} — {item.detail}
                </li>
              ))}
            </ul>
          }
        />
      ) : null}
      {nodes.length === 0 ? (
        <Empty
          data-testid="task-nodes-empty"
          description={t("teamRuns.tasks.none")}
        />
      ) : (
        <Table<TaskNodeWire>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={nodes}
          columns={[
            { title: t("teamRuns.tasks.id"), dataIndex: "id" },
            { title: t("teamRuns.tasks.title"), dataIndex: "title" },
            { title: t("teamRuns.tasks.owner"), dataIndex: "owner" },
            {
              title: t("teamRuns.tasks.status"),
              dataIndex: "status",
              render: (status: string, row) => (
                <Tag data-testid={`task-status-${row.id}`}>
                  {t(`teamRuns.taskStatus.${status}`, status)}
                </Tag>
              ),
            },
            {
              title: t("teamRuns.tasks.roundAttempt"),
              render: (_: unknown, row) => `${row.round} / ${row.attempt}`,
            },
            {
              title: t("teamRuns.tasks.dependsOn"),
              dataIndex: "dependsOn",
              render: (deps: string[]) => deps.join(", ") || "—",
            },
          ]}
        />
      )}
      <Typography.Text type="secondary" data-testid="task-edge-count">
        {t("teamRuns.tasks.edgeCount", { count: edges.length })}
      </Typography.Text>
      {nodes.length > 0 && edges.length === 0 ? (
        <Typography.Text type="secondary" data-testid="task-edges-empty">
          {t("teamRuns.tasks.noEdges")}
        </Typography.Text>
      ) : null}
    </div>
  );
}
