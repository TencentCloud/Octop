import { Dropdown, Select, Spin } from "antd";
import type { DefaultOptionType } from "antd/es/select";
import type { MenuProps } from "antd";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { useAgent, type OctopAgent } from "../context/AgentContext";
import { ownedSoloExperts, ownedTeamAgents } from "../utils/sharedExpert";
import {
  labelSelectorGroups,
  nextPickerSelection,
  showSelectorGroupLabels,
  splitBarOverflow,
  type BarChipSize,
} from "../utils/agentSelector";
import { isTeamAgent } from "../utils/teamAgent";
import { ExpertIcon } from "../pages/Experts/components/iconForName";
import RemoteExpertHint from "../pages/Chat/components/RemoteExpertHint";
import styles from "./AgentSelector.module.less";

interface AgentSelectorProps {
  style?: React.CSSProperties;
  className?: string;
  /** bar = chip row, more only on overflow; select = dropdown. */
  variant?: "auto" | "select" | "bar";
  showLabel?: boolean;
  /**
   * Include owned team hosts (memory / channels). Other pages stay
   * expert-only.
   */
  showTeams?: boolean;
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

function readBarChipSizes(
  measure: HTMLElement,
  showLabels: boolean,
): BarChipSize[] {
  const labelWidth = new Map<string, number>();
  if (showLabels) {
    for (const el of measure.querySelectorAll<HTMLElement>(
      "[data-group-label]",
    )) {
      labelWidth.set(el.dataset.groupKey ?? "", el.offsetWidth);
    }
  }
  return [...measure.querySelectorAll<HTMLElement>("[data-chip-id]")].map(
    (el) => {
      const groupKey = el.dataset.groupKey ?? "";
      return {
        id: el.dataset.chipId ?? "",
        width: el.offsetWidth,
        groupKey,
        groupLabelWidth: labelWidth.get(groupKey) ?? 0,
      };
    },
  );
}

function AgentChip({
  agent,
  active,
  onSelect,
  measure,
  groupKey,
}: {
  agent: OctopAgent;
  active: boolean;
  onSelect: (id: string) => void;
  measure?: boolean;
  groupKey?: string;
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
      tabIndex={measure ? -1 : undefined}
      data-chip-id={measure ? agent.agent_id : undefined}
      data-group-key={measure ? groupKey : undefined}
      className={`${active ? styles.chipActive : styles.chip}${
        disconnected ? ` ${styles.chipDisconnected}` : ""
      }`}
      style={{ "--chip-accent": accent } as React.CSSProperties}
      onClick={() => onSelect(agent.agent_id)}
      title={title}
    >
      <AgentIcon agent={agent} size={16} className={styles.chipIcon} />
      <span className={styles.chipName}>{agent.name}</span>
      <span
        className={styles.stateDot}
        data-state={disconnected ? "failed" : agent.state}
      />
    </button>
  );
}

function moreItemLabel(agent: OctopAgent, disconnectedLabel: string) {
  const accent = agentAccent(agent);
  const disconnected = Boolean(agent.bridge_disconnected);
  return (
    <span className={styles.optionRow}>
      <AgentIcon
        agent={agent}
        size={14}
        className={styles.optionIcon}
        style={{ color: accent }}
      />
      <span className={styles.chipName}>{agent.name}</span>
      {disconnected ? (
        <span className={styles.optionDesc}>{disconnectedLabel}</span>
      ) : null}
      <RemoteExpertHint agent={agent} compact />
      <span
        className={styles.stateDot}
        data-state={disconnected ? "failed" : agent.state}
      />
    </span>
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
  showTeams = false,
}: AgentSelectorProps) {
  const { t } = useTranslation();
  const { agents, activeAgentId, setActiveAgent, loading } = useAgent();
  const soloSelectable = useMemo(() => ownedSoloExperts(agents), [agents]);
  const allTeams = useMemo(() => ownedTeamAgents(agents), [agents]);
  const teamSelectable = useMemo(
    () => (showTeams ? allTeams : []),
    [allTeams, showTeams],
  );
  const selectable = useMemo(
    () => [...soloSelectable, ...teamSelectable],
    [soloSelectable, teamSelectable],
  );
  const expertsLabel = t("agentSelector.expertsGroup", "专家");
  const teamsLabel = t("agentSelector.teamsGroup", "团队");
  const expertGroups = useMemo(
    () =>
      labelSelectorGroups(soloSelectable, expertsLabel, (name) =>
        t("agentSelector.remoteKindGroup", {
          name,
          kind: expertsLabel,
          defaultValue: "{{name}}·{{kind}}",
        }),
      ),
    [expertsLabel, soloSelectable, t],
  );
  const teamGroups = useMemo(
    () =>
      labelSelectorGroups(teamSelectable, teamsLabel, (name) =>
        t("agentSelector.remoteKindGroup", {
          name,
          kind: teamsLabel,
          defaultValue: "{{name}}·{{kind}}",
        }),
      ),
    [t, teamSelectable, teamsLabel],
  );
  const showGroupLabels = showSelectorGroupLabels(
    expertGroups,
    teamSelectable.length,
  );
  const labeledGroups = [...expertGroups, ...teamGroups];
  const activeAgent = agents.find((agent) => agent.agent_id === activeAgentId);
  const activeIsHiddenTeam = Boolean(
    activeAgent && isTeamAgent(activeAgent) && !showTeams,
  );
  const useBar = variant !== "select";
  const currentId = activeAgentId ?? selectable[0]?.agent_id;
  const barRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [hiddenIds, setHiddenIds] = useState<string[]>([]);

  useEffect(() => {
    if (loading) return;
    const next = nextPickerSelection(activeAgentId, agents, selectable);
    if (next === undefined) return;
    setActiveAgent(next);
  }, [activeAgentId, agents, loading, selectable, setActiveAgent]);

  useLayoutEffect(() => {
    if (!useBar) return;
    const bar = barRef.current;
    const measure = measureRef.current;
    if (!bar || !measure) return;

    const read = () => {
      const moreWidth =
        measure.querySelector<HTMLElement>("[data-more-sizer]")?.offsetWidth ??
        0;
      const { hiddenIds: next } = splitBarOverflow(
        readBarChipSizes(measure, showGroupLabels),
        currentId,
        bar.clientWidth,
        moreWidth,
      );
      setHiddenIds((prev) =>
        prev.length === next.length && prev.every((id, i) => id === next[i])
          ? prev
          : next,
      );
    };

    read();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(read);
    observer.observe(bar);
    return () => observer.disconnect();
  }, [currentId, showGroupLabels, selectable, useBar]);

  if (loading) {
    return (
      <div className={`${styles.wrap} ${className ?? ""}`} style={style}>
        <Spin size="small" />
      </div>
    );
  }

  if (selectable.length === 0 && allTeams.length === 0) return null;

  const disconnectedLabel = t("agentSelector.disconnected");
  const selectOptions: DefaultOptionType[] = showGroupLabels
    ? labeledGroups.map((group) => ({
        label: group.disconnected
          ? `${group.label} · ${disconnectedLabel}`
          : group.label,
        options: group.agents.map((agent) =>
          selectOption(agent, disconnectedLabel),
        ),
      }))
    : selectable.map((agent) => selectOption(agent, disconnectedLabel));
  const hint = activeIsHiddenTeam
    ? t("agentSelector.teamNeedsExpert", {
        name: activeAgent?.name ?? "",
        defaultValue: "当前是团队「{{name}}」，此页请选择专家",
      })
    : soloSelectable.length === 0 && allTeams.length > 0
    ? t("agentSelector.expertsRequired", "此页需要专家")
    : null;
  const heading = t("agentSelector.label", "专家");
  const moreLabel = t("agentSelector.more", "更多");
  const hidden = new Set(hiddenIds);
  const visibleGroups = labeledGroups
    .map((group) => ({
      ...group,
      agents: group.agents.filter((agent) => !hidden.has(agent.agent_id)),
    }))
    .filter((group) => group.agents.length > 0);
  const overflowGroups = labeledGroups
    .map((group) => ({
      ...group,
      agents: group.agents.filter((agent) => hidden.has(agent.agent_id)),
    }))
    .filter((group) => group.agents.length > 0);
  const showMore = overflowGroups.length > 0;
  const moreItems: MenuProps["items"] = showGroupLabels
    ? overflowGroups.map((group) => ({
        type: "group",
        key: `${group.key}-${group.label}`,
        label: group.disconnected
          ? `${group.label} · ${disconnectedLabel}`
          : group.label,
        children: group.agents.map((agent) => ({
          key: agent.agent_id,
          label: moreItemLabel(agent, disconnectedLabel),
        })),
      }))
    : overflowGroups.flatMap((group) =>
        group.agents.map((agent) => ({
          key: agent.agent_id,
          label: moreItemLabel(agent, disconnectedLabel),
        })),
      );

  const renderGroup = (
    group: (typeof labeledGroups)[number],
    measure: boolean,
  ) => {
    const groupKey = `${group.key}-${group.label}`;
    return (
      <div key={groupKey} className={styles.group}>
        {showGroupLabels ? (
          <span
            className={styles.groupLabel}
            data-group-label={measure ? "" : undefined}
            data-group-key={measure ? groupKey : undefined}
          >
            {group.label}
            {group.disconnected ? ` · ${disconnectedLabel}` : ""}
          </span>
        ) : null}
        {group.agents.map((agent) => (
          <AgentChip
            key={agent.agent_id}
            agent={agent}
            active={agent.agent_id === currentId}
            onSelect={setActiveAgent}
            measure={measure}
            groupKey={groupKey}
          />
        ))}
      </div>
    );
  };

  return (
    <div className={`${styles.wrap} ${className ?? ""}`} style={style}>
      <div className={styles.row}>
        {showLabel && !showGroupLabels ? (
          <span className={styles.label}>{heading}</span>
        ) : null}

        {useBar ? (
          selectable.length > 0 ? (
            <div className={styles.bar} ref={barRef}>
              <div className={styles.measure} ref={measureRef} aria-hidden>
                {labeledGroups.map((group) => renderGroup(group, true))}
                <button
                  type="button"
                  className={styles.moreBtn}
                  data-more-sizer=""
                  tabIndex={-1}
                >
                  {moreLabel}
                  <ChevronDown size={12} aria-hidden />
                </button>
              </div>
              <div data-testid="agent-selector-chips" className={styles.track}>
                {visibleGroups.map((group) => renderGroup(group, false))}
              </div>
              {showMore ? (
                <Dropdown
                  trigger={["click"]}
                  menu={{
                    className: styles.moreMenu,
                    items: moreItems,
                    onClick: ({ key }) => setActiveAgent(key),
                  }}
                >
                  <button type="button" className={styles.moreBtn}>
                    {moreLabel}
                    <ChevronDown size={12} aria-hidden />
                  </button>
                </Dropdown>
              ) : null}
            </div>
          ) : null
        ) : (
          <Select
            className={styles.select}
            value={
              currentId &&
              selectable.some((agent) => agent.agent_id === currentId)
                ? currentId
                : undefined
            }
            placeholder={heading}
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
                        {disconnectedLabel}
                      </div>
                    ) : agent.description ? (
                      <div className={styles.optionDesc}>
                        {agent.description}
                      </div>
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
      {hint ? <span className={styles.hint}>{hint}</span> : null}
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
