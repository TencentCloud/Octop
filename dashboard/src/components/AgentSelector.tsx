import { Select, Spin } from "antd";
import { useEffect, useMemo, useRef } from "react";
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useAgent, type OctopAgent } from "../context/AgentContext";
import { ownedSoloExperts } from "../utils/sharedExpert";
import { ExpertIcon } from "../pages/Experts/components/iconForName";
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
  tabRef,
}: {
  agent: OctopAgent;
  active: boolean;
  onSelect: (id: string) => void;
  tabRef?: Map<string, HTMLButtonElement>;
}) {
  const accent = agentAccent(agent);
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      ref={(el) => {
        if (tabRef) {
          if (el) tabRef.set(agent.agent_id, el);
          else tabRef.delete(agent.agent_id);
        }
      }}
      className={active ? styles.chipActive : styles.chip}
      style={{ "--chip-accent": accent } as React.CSSProperties}
      onClick={() => onSelect(agent.agent_id)}
      title={agent.description ?? agent.name}
    >
      <AgentIcon agent={agent} size={16} className={styles.chipIcon} />
      <span className={styles.chipName}>{agent.name}</span>
      <span className={styles.stateDot} data-state={agent.state} aria-hidden />
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
  const barTabRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

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
          onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
            // Roving focus: Arrow/Home/End move selection without leaving
            // the list (audit A11Y-9 — the tablist previously had no
            // keyboard navigation and no exposed selection).
            const keys = ["ArrowRight", "ArrowLeft", "Home", "End"];
            if (!keys.includes(event.key) || selectable.length === 0) return;
            event.preventDefault();
            const idx = selectable.findIndex((a) => a.agent_id === currentId);
            const next =
              event.key === "ArrowRight"
                ? (idx + 1) % selectable.length
                : event.key === "ArrowLeft"
                ? (idx - 1 + selectable.length) % selectable.length
                : event.key === "Home"
                ? 0
                : selectable.length - 1;
            const target = selectable[next];
            if (!target) return;
            setActiveAgent(target.agent_id);
            barTabRefs.current.get(target.agent_id)?.focus();
          }}
        >
          {selectable.map((agent) => (
            <AgentChip
              key={agent.agent_id}
              agent={agent}
              active={agent.agent_id === currentId}
              onSelect={setActiveAgent}
              tabRef={barTabRefs.current}
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
          options={selectable.map((agent) => {
            const accent = agentAccent(agent);
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
                </span>
              ),
              title: agent.name,
            };
          })}
          optionRender={(opt) => {
            const agent = selectable.find((a) => a.agent_id === opt.value);
            if (!agent) return opt.label;
            const accent = agentAccent(agent);
            return (
              <div className={styles.optionRowMulti}>
                <AgentIcon
                  agent={agent}
                  size={14}
                  className={styles.optionIcon}
                  style={{ color: accent }}
                />
                <div className={styles.optionMeta}>
                  <div className={styles.optionName} title={agent.name}>
                    {agent.name}
                  </div>
                  {agent.description ? (
                    <div
                      className={styles.optionDesc}
                      title={agent.description}
                    >
                      {agent.description}
                    </div>
                  ) : null}
                </div>
                <span
                  className={styles.stateDot}
                  data-state={agent.state}
                  aria-hidden
                />
              </div>
            );
          }}
        />
      )}
    </div>
  );
}
