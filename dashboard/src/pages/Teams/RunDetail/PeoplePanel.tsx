/**
 * `PeoplePanel` — who is on the run and **how loaded they are**.
 *
 * Load comes from **DB tasks in flight** (`TaskNodeWire.owner` + storage status), *not*
 * from `TeamJobTracker`: the tracker is an in-process view of jobs this server happens
 * to know about, while the run's task board is the persisted fact. Using the tracker
 * would make a member look idle after a restart.
 *
 * An owner with **no tasks** shows `0 tasks`, and a run with **no tasks at all** shows an
 * empty board hint — the two are different facts and are rendered differently (a member
 * with zero rows is not "unloaded", it is "unassigned").
 *
 * Presentational (AGENTS.md §5): no fetching — the caller owns the request.
 */

import { Empty, Table, Tag } from "antd";
import { useTranslation } from "react-i18next";

import type { MemberWire, TaskNodeWire } from "../../../api/modules/teamRuns";
import { IN_FLIGHT_STATUSES } from "../../../api/modules/teamRuns";

export interface MemberLoad {
  role: string;
  agent_id: string;
  is_lead: boolean;
  /** Tasks on the board owned by this role. */
  tasks: number;
  /** Tasks whose storage status is not done/cancelled. */
  inFlight: number;
}

/** Pure: pair members with their task counts (empty board ⇒ zeros, not "unknown"). */
export function memberLoads(
  members: MemberWire[],
  tasks: TaskNodeWire[],
): MemberLoad[] {
  return members.map((member) => {
    const owned = tasks.filter((task) => task.owner === member.role);
    return {
      role: member.role,
      agent_id: member.agent_id,
      is_lead: member.is_lead,
      tasks: owned.length,
      inFlight: owned.filter((task) => IN_FLIGHT_STATUSES.includes(task.status))
        .length,
    };
  });
}

export interface PeoplePanelProps {
  members: MemberWire[];
  tasks: TaskNodeWire[];
  loading?: boolean;
}

export default function PeoplePanel({
  members,
  tasks,
  loading,
}: PeoplePanelProps) {
  const { t } = useTranslation();
  if (!members.length) {
    return (
      <Empty
        data-testid="people-empty"
        description={
          loading ? t("teamRuns.people.loading") : t("teamRuns.people.none")
        }
      />
    );
  }
  const rows = memberLoads(members, tasks);
  return (
    <div data-testid="people-panel">
      <Table<MemberLoad>
        rowKey="agent_id"
        size="small"
        pagination={false}
        dataSource={rows}
        columns={[
          {
            title: t("teamRuns.people.role"),
            dataIndex: "role",
            render: (role: string, row) => (
              <span>
                {role}
                {row.is_lead ? (
                  <Tag
                    className="ml-1"
                    color="gold"
                    data-testid={`member-lead-${row.role}`}
                  >
                    {t("teamRuns.people.lead")}
                  </Tag>
                ) : null}
              </span>
            ),
          },
          { title: t("teamRuns.people.agent"), dataIndex: "agent_id" },
          {
            title: t("teamRuns.people.tasks"),
            dataIndex: "tasks",
            render: (count: number, row) => (
              <span data-testid={`member-tasks-${row.role}`}>{count}</span>
            ),
          },
          {
            title: t("teamRuns.people.inFlight"),
            dataIndex: "inFlight",
            render: (count: number, row) => (
              <span data-testid={`member-inflight-${row.role}`}>{count}</span>
            ),
          },
        ]}
      />
      {tasks.length === 0 ? (
        <div
          data-testid="people-board-empty"
          className="mt-2 text-xs opacity-70"
        >
          {t("teamRuns.people.boardEmpty")}
        </div>
      ) : null}
    </div>
  );
}
