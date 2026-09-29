/**
 * `RosterEditor` — the team roster page (T-34 ②, AM-1/AM-4).
 *
 * What it shows, and where every fact comes from:
 *
 * * **roles** — read from `GET /api/teams/{team_id}/roster` (i.e. `.octop/manifest.json`,
 *   AM-1's single authority). The component holds **no role vocabulary**: T-33 moved
 *   "who is what" out of prose and into data, so a list here would move it back.
 * * **the lead / host** — `lead_agent_id` (data). The host row is **pinned to the top**
 *   and tagged 队长/主持人; `null` means the team host chairs it itself, which is stated
 *   as such rather than rendered as "no lead".
 * * **cut roles** — `gate_detail.skipped_roles` (written by `run_service.create()`):
 *   AM-1's hard rule is 「被裁可见、不静默丢弃」, so they appear as their own section
 *   (same shape as `pages/Teams/RunDetail/PhaseStepper.tsx`).
 * * **member load** — from the run's **DB task board** (in-flight task counts), passed in
 *   by the caller. **Never** from `TeamJobTracker` (R9): the tracker is this process's
 *   view of jobs, so a restart would make a busy member look idle.
 *
 * Boundary (`AGENTS.md` §5): fetching and saving go through `api/` — via the injectable
 * `load`/`save` props, which default to the typed client in `api/modules/teams.ts`.
 * The component never calls `fetch` itself, and it never writes on its own: saving only
 * happens when the caller-provided `save` is invoked from an explicit action.
 */

import {
  Alert,
  Button,
  Empty,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  getTeamRoster,
  putTeamRoster,
  type TeamRoster,
  type TeamRosterMember,
} from "../../api/modules/teams";

export interface RosterMemberLoad {
  role: string;
  agent_id: string;
  /** Tasks on the run board owned by this role (caller supplies; DB-derived). */
  tasks: number;
  /** Of those, the ones not done/cancelled. */
  inFlight: number;
}

export interface RosterEditorProps {
  teamId: string;
  /** `gate_detail.skipped_roles` — roles the tier cap cut (visible, never silent). */
  skippedRoles?: string[];
  /** Loads from the roster endpoint by default; injectable for hosts/tests. */
  load?: (teamId: string) => Promise<TeamRoster>;
  /** Saves through `PUT …/roster` by default; injectable for hosts/tests. */
  save?: (
    teamId: string,
    body: { members: TeamRosterMember[]; lead_agent_id?: string | null },
  ) => Promise<TeamRoster>;
  /** Opens a member's profile drawer. Without it the rows are read-only. */
  onOpenProfile?: (agentId: string) => void;
  /** Optional per-role load, computed by the caller from the DB task board. */
  loads?: RosterMemberLoad[];
}

/** Lead first, then the manifest order — the host is pinned, never sorted away. */
export function orderRoster(roster: TeamRoster): TeamRosterMember[] {
  const lead = roster.lead_agent_id;
  const members = [...roster.members];
  if (!lead) return members;
  const index = members.findIndex((member) => member.agent_id === lead);
  if (index <= 0) return members;
  const [host] = members.splice(index, 1);
  return [host, ...members];
}

export function isLeadMember(
  member: TeamRosterMember,
  leadAgentId: string | null,
): boolean {
  return Boolean(leadAgentId) && member.agent_id === leadAgentId;
}

export default function RosterEditor({
  teamId,
  skippedRoles = [],
  load = getTeamRoster,
  save = putTeamRoster,
  onOpenProfile,
  loads = [],
}: RosterEditorProps) {
  const { t } = useTranslation();
  const [roster, setRoster] = useState<TeamRoster | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchRoster = useCallback(async () => {
    setError(null);
    try {
      setRoster(await load(teamId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [teamId, load]);

  // `load` is a prop with a stable default import; the dependency list stays
  // `[fetchRoster]` so a re-render cannot re-trigger an infinite fetch loop
  // (the T-38 lesson: localised text must stay out of effect deps).
  useEffect(() => {
    void fetchRoster();
  }, [fetchRoster]);

  const persist = useCallback(
    async (members: TeamRosterMember[], leadAgentId: string | null) => {
      setSaving(true);
      try {
        setRoster(await save(teamId, { members, lead_agent_id: leadAgentId }));
      } finally {
        setSaving(false);
      }
    },
    [teamId, save],
  );

  const loadOf = (role: string): RosterMemberLoad | undefined =>
    loads.find((item) => item.role === role);

  if (error) {
    return (
      <Alert type="error" showIcon data-testid="roster-error" message={error} />
    );
  }
  if (!roster) {
    return <Spin data-testid="roster-loading" />;
  }
  const ordered = orderRoster(roster);

  return (
    <div data-testid="roster-editor" className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Typography.Title level={4} className="m-0">
          {t("teamRuns.roster.title")}
        </Typography.Title>
        <Button
          size="small"
          loading={saving}
          data-testid="roster-save"
          onClick={() => void persist(ordered, roster.lead_agent_id)}
        >
          {t("teamRuns.roster.save")}
        </Button>
      </div>

      {roster.lead_agent_id ? null : (
        <Typography.Text type="secondary" data-testid="roster-host-chairs">
          {t("teamRuns.roster.hostChairs")}
        </Typography.Text>
      )}

      {ordered.length === 0 ? (
        <Empty
          data-testid="roster-empty"
          description={t("teamRuns.roster.none")}
        />
      ) : (
        <Table<TeamRosterMember>
          rowKey="agent_id"
          size="small"
          pagination={false}
          data-testid="roster-table"
          dataSource={ordered}
          rowClassName={(row) =>
            isLeadMember(row, roster.lead_agent_id) ? "roster-lead-row" : ""
          }
          columns={[
            {
              title: t("teamRuns.roster.role"),
              dataIndex: "role",
              render: (role: string | null, row) => {
                const lead = isLeadMember(row, roster.lead_agent_id);
                return (
                  <span className="flex items-center gap-1">
                    <Tag data-testid={`roster-role-${row.agent_id}`}>
                      {role ?? t("teamRuns.roster.roleMissing")}
                    </Tag>
                    {lead ? (
                      <Tag
                        color="gold"
                        data-testid={`roster-lead-${row.agent_id}`}
                      >
                        {t("teamRuns.roster.leadBadge")}
                      </Tag>
                    ) : null}
                  </span>
                );
              },
            },
            {
              title: t("teamRuns.roster.agent"),
              dataIndex: "agent_id",
              render: (agentId: string) =>
                onOpenProfile ? (
                  <Button
                    type="link"
                    size="small"
                    data-testid={`roster-open-${agentId}`}
                    onClick={() => onOpenProfile(agentId)}
                  >
                    {agentId}
                  </Button>
                ) : (
                  <span data-testid={`roster-agent-${agentId}`}>{agentId}</span>
                ),
            },
            {
              title: t("teamRuns.roster.tasks"),
              dataIndex: "role",
              render: (role: string | null, row) => {
                const stats = loadOf(String(role ?? ""));
                return (
                  <span data-testid={`roster-load-${row.agent_id}`}>
                    {stats
                      ? `${stats.inFlight} / ${stats.tasks}`
                      : t("teamRuns.roster.loadUnknown")}
                  </span>
                );
              },
            },
          ]}
        />
      )}

      {skippedRoles.length > 0 ? (
        <Alert
          type="info"
          showIcon
          data-testid="roster-skipped-roles"
          message={t("teamRuns.roster.skippedTitle")}
          description={
            <span data-testid="roster-skipped-list">
              {skippedRoles.join(" / ")} — {t("teamRuns.roster.skippedHint")}
            </span>
          }
        />
      ) : null}

      {loads.length === 0 ? (
        <Tooltip title={t("teamRuns.roster.loadSourceHint")}>
          <Typography.Text type="secondary" data-testid="roster-load-source">
            {t("teamRuns.roster.loadSource")}
          </Typography.Text>
        </Tooltip>
      ) : null}
    </div>
  );
}
