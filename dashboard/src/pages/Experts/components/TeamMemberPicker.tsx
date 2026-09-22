import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "antd";
import { Check } from "lucide-react";
import { isOwnedExpert } from "../../../utils/sharedExpert";
import { ExpertIcon } from "./iconForName";
import styles from "../index.module.less";

export interface TeamMemberOption {
  agent_id: string;
  name: string;
  description?: string | null;
  color?: string | null;
  icon_name?: string | null;
  icon_url?: string | null;
  kind?: string;
  is_shared?: boolean;
  is_owner?: boolean;
}

interface TeamMemberPickerProps {
  value?: string[];
  onChange?: (ids: string[]) => void;
  experts: TeamMemberOption[];
}

export function isPickableExpert(item: TeamMemberOption): boolean {
  if (item.kind === "team") return false;
  return isOwnedExpert(item) || Boolean(item.is_shared);
}

/** Keep only currently pickable ids — save applies this full set, not incremental adds. */
export function selectedRosterIds(
  selected: string[] | undefined,
  experts: TeamMemberOption[],
): string[] {
  const allowed = new Set(
    experts.filter(isPickableExpert).map((item) => item.agent_id),
  );
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of selected ?? []) {
    if (!allowed.has(id) || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

export default function TeamMemberPicker({
  value,
  onChange,
  experts,
}: TeamMemberPickerProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const selected = useMemo(
    () => selectedRosterIds(value, experts),
    [value, experts],
  );
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const candidates = useMemo(() => {
    const byId = new Map<string, TeamMemberOption>();
    for (const item of experts) {
      if (!isPickableExpert(item)) continue;
      byId.set(item.agent_id, item);
    }
    return [...byId.values()];
  }, [experts]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = needle
      ? candidates.filter((item) => {
          const name = item.name.toLowerCase();
          const desc = (item.description ?? "").toLowerCase();
          return name.includes(needle) || desc.includes(needle);
        })
      : candidates;
    return [...rows].sort((left, right) => {
      const leftOn = selectedSet.has(left.agent_id) ? 0 : 1;
      const rightOn = selectedSet.has(right.agent_id) ? 0 : 1;
      if (leftOn !== rightOn) return leftOn - rightOn;
      return left.name.localeCompare(right.name);
    });
  }, [candidates, query, selectedSet]);

  const toggle = (id: string) => {
    onChange?.(
      selectedSet.has(id)
        ? selected.filter((item) => item !== id)
        : [...selected, id],
    );
  };

  return (
    <div className={styles.memberPicker}>
      <Input
        allowClear
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t("experts.teams.membersSearch")}
      />
      <div className={styles.memberPickerMeta}>
        {t("experts.teams.membersSelected", { count: selected.length })}
      </div>
      {filtered.length === 0 ? (
        <div className={styles.memberPickerEmpty}>
          {t("experts.teams.membersEmpty")}
        </div>
      ) : (
        <div className={styles.memberPickerGrid}>
          {filtered.map((expert) => {
            const active = selectedSet.has(expert.agent_id);
            const accent = expert.color || "#0d9488";
            return (
              <button
                key={expert.agent_id}
                type="button"
                className={`${styles.memberPickCard}${
                  active ? ` ${styles.memberPickCardSelected}` : ""
                }`}
                onClick={() => toggle(expert.agent_id)}
                aria-pressed={active}
              >
                {active && (
                  <span className={styles.memberPickCheck} aria-hidden>
                    <Check size={11} strokeWidth={3} />
                  </span>
                )}
                <div
                  className={styles.memberPickIcon}
                  style={{ color: accent, background: `${accent}1a` }}
                >
                  <ExpertIcon
                    iconUrl={expert.icon_url}
                    iconName={expert.icon_name}
                    size={expert.icon_url ? 36 : 18}
                  />
                </div>
                <div className={styles.memberPickBody}>
                  <div className={styles.memberPickName}>{expert.name}</div>
                  <div className={styles.memberPickDesc}>
                    {expert.description?.trim() || "\u00a0"}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function mergeTeamPickerExperts(
  experts: TeamMemberOption[],
  extras: TeamMemberOption[] = [],
): TeamMemberOption[] {
  const byId = new Map<string, TeamMemberOption>();
  for (const item of extras) byId.set(item.agent_id, item);
  for (const item of experts) byId.set(item.agent_id, item);
  return [...byId.values()];
}
