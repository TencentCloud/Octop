import { useMemo, useState } from "react";
import { Button, Input, Popover } from "antd";
import { ChevronDown, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { ProjectMember } from "../../../api/modules/projects";
import styles from "./AgentPicker.module.less";

/**
 * Recipient picker for the project quick input (PLAN §2).
 *
 * Lightweight by contract: it is **not** a shared widget — `TaskCreateModal`'s
 * assignee picker stays private and its diff must stay empty (§3.2 ruling B②),
 * so this only covers what D2 needs: single choice, type-to-filter, no
 * persistence.
 *
 * ★ It does **not** predict agent access rights (PLAN §3.1 ruling A①): the
 * listing is just the project's `subject_type === 'agent'` members, and an agent
 * this user cannot reach is rejected by the server (`assert_agent_access` →
 * WS 4003/4404), which the caller surfaces through the normal failure path
 * (explicit error + kept input). Predicting it would need new API fields.
 */
export interface AgentPickerProps {
  agents: ProjectMember[];
  value: ProjectMember | null;
  onChange: (next: ProjectMember) => void;
  disabled?: boolean;
  filterPlaceholder?: string;
  emptyText?: string;
}

export function AgentPicker({
  agents,
  value,
  onChange,
  disabled = false,
  filterPlaceholder,
  emptyText,
}: AgentPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return agents;
    // Case-insensitive substring match on the subject id (PLAN §2.1).
    return agents.filter((agent) =>
      agent.subject_id.toLowerCase().includes(needle),
    );
  }, [agents, query]);

  const close = () => {
    setOpen(false);
    setQuery("");
  };

  const content = (
    /* ``group`` (not ``listbox``): the children stay real buttons carrying
       ``aria-pressed`` for the single choice, and a listbox may only own
       ``option`` children. The frozen key names the whole recipient list — filter
       included — so screen readers announce it on entry instead of an
       unlabelled cluster of buttons. */
    <div
      className={styles.panel}
      role="group"
      aria-label={t("projects.quickInputRecipientListLabel")}
      data-testid="quick-input-recipient-list"
    >
      <Input
        className={styles.filter}
        size="small"
        allowClear
        prefix={<Search size={12} />}
        value={query}
        placeholder={
          filterPlaceholder ?? t("projects.quickInputRecipientFilter")
        }
        aria-label={
          filterPlaceholder ?? t("projects.quickInputRecipientFilter")
        }
        data-testid="quick-input-recipient-filter"
        onChange={(event) => setQuery(event.target.value)}
      />
      {filtered.length === 0 ? (
        <div className={styles.empty} data-testid="quick-input-recipient-empty">
          {emptyText ?? t("projects.quickInputRecipientEmpty")}
        </div>
      ) : (
        filtered.map((agent) => (
          <button
            key={agent.subject_id}
            type="button"
            aria-pressed={agent.subject_id === value?.subject_id}
            className={`${styles.option} ${
              agent.subject_id === value?.subject_id ? styles.optionActive : ""
            }`}
            data-testid={`quick-input-recipient-option-${agent.subject_id}`}
            onClick={() => {
              onChange(agent);
              close();
            }}
          >
            {agent.subject_id}
          </button>
        ))
      )}
    </div>
  );

  return (
    <Popover
      open={open}
      trigger="click"
      placement="bottomLeft"
      content={content}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <Button
        size="small"
        disabled={disabled}
        className={styles.trigger}
        data-testid="quick-input-recipient-trigger"
        aria-label={t("projects.quickInputRecipientTrigger")}
        icon={<ChevronDown size={12} />}
      >
        {/* 明示发给谁：沿用既有 testid（PLAN §6 只增不删）。 */}
        <span data-testid="quick-input-target">
          {value
            ? t("projects.quickInputTarget", { name: value.subject_id })
            : t("projects.quickInputRecipientTrigger")}
        </span>
      </Button>
    </Popover>
  );
}

export default AgentPicker;
