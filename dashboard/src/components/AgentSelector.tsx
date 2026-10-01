import { Select, Spin } from "antd";
import type { DefaultOptionType } from "antd/es/select";
import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useAgent, type OctopAgent } from "../context/AgentContext";
import { ownedSoloExperts } from "../utils/sharedExpert";
import { groupExpertsByConnection } from "../utils/remoteExpert";
import { ExpertIcon } from "../pages/Experts/components/iconForName";
import RemoteExpertHint from "../pages/Chat/components/RemoteExpertHint";
import styles from "./AgentSelector.module.less";

interface AgentSelectorProps {
  style?: React.CSSProperties;
  className?: string;
  /** auto = chips when ≤6 agents, otherwise select */
  variant?: "auto" | "select" | "bar";
  showLabel?: boolean;
}

function agentAccent(agent: OctopAgent): string {
  const cfg = agent.config ?? {};
  const fromConfig = typeof cfg.color === "string" ? cfg.color : null;
  return agent.color || fromConfig || "#2563eb";
}

function AgentIcon({
  agent,
  size,
  className,
  style,
}: {
  agent: OctopAgent;
  size: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const photo = Boolean(agent.icon_url?.trim());
  return (
    <span className={className} style={style}>
      <ExpertIcon
        iconUrl={agent.icon_url}
        iconName={agent.icon_name}
        size={photo ? size : Math.max(12, Math.round(size * 0.55))}
      />
    </span>
  );
}

function AgentChip({
  agent,
  active,
  onSelect,
}: {
  agent: OctopAgent;
  active: boolean;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const accent = agentAccent(agent);
  const disconnected = Boolean(agent.bridge_disconnected);
  const title = disconnected
    ? `${agent.name} · ${t("agentSelector.disconnected")}`
    : agent.description ?? agent.name;
  return (
    <button
      type="button"
      className={`${active ? styles.chipActive : styles.chip}${
        disconnected ? ` ${styles.chipDisconnected}` : ""
      }`}
      style={{ "--chip-accent": accent } as React.CSSProperties}
      onClick={() => onSelect(agent.agent_id)}
      title={title}
    >
      <AgentIcon agent={agent} size={16} className={styles.chipIcon} />
      <span className={styles.chipName}>{agent.name}</span>
      <RemoteExpertHint agent={agent} compact />
      <span
        className={styles.stateDot}
        data-state={disconnected ? "failed" : agent.state}
      />
    </button>
  );
}

/**
 * Agent picker for agent-scoped pages. Persists selection via AgentContext.
 */
export default function AgentSelector({
  style,
  className,
  variant = "auto",
  showLabel = true,
}: AgentSelectorProps) {
  const { t } = useTranslation();
  const { agents, activeAgentId, setActiveAgent, loading } = useAgent();
  const selectable = useMemo(() => ownedSoloExperts(agents), [agents]);
  const groups = useMemo(
    () => groupExpertsByConnection(selectable, t("agentSelector.localGroup")),
    [selectable, t],
  );
  const showGroups = groups.length > 1;

  useEffect(() => {
    if (loading || selectable.length === 0) return;
    if (
      activeAgentId &&
      selectable.some((agent) => agent.agent_id === activeAgentId)
    ) {
      return;
    }
    setActiveAgent(selectable[0]?.agent_id ?? null);
  }, [activeAgentId, loading, selectable, setActiveAgent]);

  if (loading) {
    return (
      <div className={`${styles.wrap} ${className ?? ""}`} style={style}>
        <Spin size="small" />
      </div>
    );
  }

  if (selectable.length === 0) return null;

  const currentId = activeAgentId ?? selectable[0]?.agent_id;
  const useBar =
    variant === "bar" || (variant === "auto" && selectable.length <= 6);

  const selectOptions: DefaultOptionType[] = showGroups
    ? groups.map((group) => ({
        label: group.disconnected
          ? `${group.label} · ${t("agentSelector.disconnected")}`
          : group.label,
        options: group.agents.map((agent) =>
          selectOption(agent, t("agentSelector.disconnected")),
        ),
      }))
    : selectable.map((agent) =>
        selectOption(agent, t("agentSelector.disconnected")),
      );

  return (
    <div className={`${styles.wrap} ${className ?? ""}`} style={style}>
      {showLabel && (
        <span className={styles.label}>{t("agentSelector.label")}</span>
      )}

      {useBar ? (
        <div
          className={styles.bar}
          role="tablist"
          aria-label={t("agentSelector.label")}
        >
          {groups.map((group) => (
            <div key={group.key} className={styles.group}>
              {showGroups ? (
                <span className={styles.groupLabel}>
                  {group.label}
                  {group.disconnected
                    ? ` · ${t("agentSelector.disconnected")}`
                    : ""}
                </span>
              ) : null}
              {group.agents.map((agent) => (
                <AgentChip
                  key={agent.agent_id}
                  agent={agent}
                  active={agent.agent_id === currentId}
                  onSelect={setActiveAgent}
                />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <Select
          className={styles.select}
          value={currentId}
          onChange={(id) => setActiveAgent(id)}
          listHeight={360}
          popupMatchSelectWidth={320}
          optionLabelProp="label"
          options={selectOptions}
          optionRender={(opt) => {
            const agent = selectable.find((a) => a.agent_id === opt.value);
            if (!agent) return opt.label;
            const accent = agentAccent(agent);
            const disconnected = Boolean(agent.bridge_disconnected);
            return (
              <div className={styles.optionRowMulti}>
                <AgentIcon
                  agent={agent}
                  size={14}
                  className={styles.optionIcon}
                  style={{ color: accent }}
                />
                <div className={styles.optionMeta}>
                  <div className={styles.optionName}>{agent.name}</div>
                  {disconnected ? (
                    <div className={styles.optionDesc}>
                      {t("agentSelector.disconnected")}
                    </div>
                  ) : agent.description ? (
                    <div className={styles.optionDesc}>{agent.description}</div>
                  ) : null}
                </div>
                <RemoteExpertHint agent={agent} compact />
                <span
                  className={styles.stateDot}
                  data-state={disconnected ? "failed" : agent.state}
                />
              </div>
            );
          }}
        />
      )}
    </div>
  );
}

function selectOption(agent: OctopAgent, disconnectedLabel: string) {
  const accent = agentAccent(agent);
  const disconnected = Boolean(agent.bridge_disconnected);
  return {
    value: agent.agent_id,
    label: (
      <span className={styles.optionRow}>
        <AgentIcon
          agent={agent}
          size={14}
          className={styles.optionIcon}
          style={{ color: accent }}
        />
        <span className={styles.chipName}>{agent.name}</span>
        <RemoteExpertHint agent={agent} compact />
      </span>
    ),
    title: disconnected ? `${agent.name} · ${disconnectedLabel}` : agent.name,
  };
}
