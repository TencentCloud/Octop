import { Select, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { useAgent, type OctopAgent } from "../context/AgentContext";
import { iconForName } from "../pages/Experts/components/iconForName";
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

function AgentChip({
  agent,
  active,
  onSelect,
}: {
  agent: OctopAgent;
  active: boolean;
  onSelect: (id: string) => void;
}) {
  const accent = agentAccent(agent);
  return (
    <button
      type="button"
      className={active ? styles.chipActive : styles.chip}
      style={{ "--chip-accent": accent } as React.CSSProperties}
      onClick={() => onSelect(agent.agent_id)}
      title={agent.description ?? agent.name}
    >
      <span className={styles.chipIcon}>
        {iconForName(agent.icon_name, 12)}
      </span>
      <span className={styles.chipName}>{agent.name}</span>
      <span className={styles.stateDot} data-state={agent.state} />
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

  if (loading) {
    return (
      <div className={`${styles.wrap} ${className ?? ""}`} style={style}>
        <Spin size="small" />
      </div>
    );
  }

  if (agents.length === 0) return null;

  const currentId = activeAgentId ?? agents[0]?.agent_id;
  const useBar =
    variant === "bar" || (variant === "auto" && agents.length <= 6);

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
          {agents.map((agent) => (
            <AgentChip
              key={agent.agent_id}
              agent={agent}
              active={agent.agent_id === currentId}
              onSelect={setActiveAgent}
            />
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
          options={agents.map((agent) => {
            const accent = agentAccent(agent);
            return {
              value: agent.agent_id,
              label: (
                <span className={styles.optionRow}>
                  <span className={styles.optionIcon} style={{ color: accent }}>
                    {iconForName(agent.icon_name, 12)}
                  </span>
                  <span className={styles.chipName}>{agent.name}</span>
                </span>
              ),
              title: agent.name,
            };
          })}
          optionRender={(opt) => {
            const agent = agents.find((a) => a.agent_id === opt.value);
            if (!agent) return opt.label;
            const accent = agentAccent(agent);
            return (
              <div className={styles.optionRowMulti}>
                <span className={styles.optionIcon} style={{ color: accent }}>
                  {iconForName(agent.icon_name, 12)}
                </span>
                <div className={styles.optionMeta}>
                  <div className={styles.optionName}>{agent.name}</div>
                  {agent.description ? (
                    <div className={styles.optionDesc}>{agent.description}</div>
                  ) : null}
                </div>
                <span className={styles.stateDot} data-state={agent.state} />
              </div>
            );
          }}
        />
      )}
    </div>
  );
}
