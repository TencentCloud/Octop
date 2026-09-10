import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Plug } from "lucide-react";
import type { ChatConnectorOption } from "./ConnectorPickerPopover";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import type { AgentSubagentSummary } from "../../../api/modules/subagents";
import ExpertAgentAvatar from "./ExpertAgentAvatar";
import styles from "../index.module.less";

export type MentionAgentOption = ChatAgentOption;

export type MentionPick =
  | { kind: "connector"; name: string; label: string }
  | { kind: "agent"; agent_id: string; label: string }
  | { kind: "subagent"; slug: string; label: string };

export function buildMentionItems(
  query: string,
  connectors: ChatConnectorOption[],
  agents: MentionAgentOption[] = [],
  subagents: AgentSubagentSummary[] = [],
): MentionPick[] {
  const q = query.trim().toLowerCase();
  const out: MentionPick[] = [];
  for (const c of connectors) {
    if (
      q &&
      !c.label.toLowerCase().includes(q) &&
      !c.mcp_server_name.toLowerCase().includes(q)
    ) {
      continue;
    }
    out.push({ kind: "connector", name: c.mcp_server_name, label: c.label });
  }
  for (const a of agents) {
    if (
      q &&
      !a.name.toLowerCase().includes(q) &&
      !a.agent_id.toLowerCase().includes(q)
    )
      continue;
    out.push({ kind: "agent", agent_id: a.agent_id, label: a.name });
  }
  for (const s of subagents) {
    const label = s.name || s.slug;
    if (
      q &&
      !label.toLowerCase().includes(q) &&
      !s.slug.toLowerCase().includes(q)
    ) {
      continue;
    }
    out.push({ kind: "subagent", slug: s.slug, label });
  }
  return out;
}

interface MentionPickerMenuProps {
  query: string;
  connectors: ChatConnectorOption[];
  agents?: MentionAgentOption[];
  subagents?: AgentSubagentSummary[];
  activeIndex: number;
  onSelect: (pick: MentionPick) => void;
  onHover: (index: number) => void;
}

export default function MentionPickerMenu({
  query,
  connectors,
  agents = [],
  subagents = [],
  activeIndex,
  onSelect,
  onHover,
}: MentionPickerMenuProps) {
  const { t, i18n } = useTranslation();

  const items = useMemo(
    () => buildMentionItems(query, connectors, agents, subagents),
    [query, connectors, agents, subagents],
  );

  const connSection = i18n.language.startsWith("zh") ? "连接器" : "Connectors";
  const agentSection = i18n.language.startsWith("zh") ? "专家" : "Experts";
  const subagentSection = i18n.language.startsWith("zh")
    ? "子智能体"
    : "Subagents";

  const sectionFor = (item: MentionPick) => {
    if (item.kind === "connector") return connSection;
    if (item.kind === "subagent") return subagentSection;
    return agentSection;
  };

  if (items.length === 0) {
    return (
      <div className={styles.mentionMenu}>
        <div className={styles.mentionEmpty}>
          {t("mention.empty", "No matches")}
        </div>
      </div>
    );
  }

  let lastSection = "";
  let flatIndex = -1;

  return (
    <div className={styles.mentionMenu}>
      {items.map((item) => {
        const section = sectionFor(item);
        const showHeader = section !== lastSection;
        lastSection = section;
        flatIndex += 1;
        const idx = flatIndex;
        const active = idx === activeIndex;
        let icon;
        if (item.kind === "connector") {
          icon = <Plug size={14} />;
        } else if (item.kind === "subagent") {
          const sub = subagents.find((s) => s.slug === item.slug);
          icon = <span aria-hidden>{sub?.emoji || "🤖"}</span>;
        } else {
          const agent = agents.find((a) => a.agent_id === item.agent_id);
          icon = (
            <ExpertAgentAvatar
              iconName={agent?.icon_name}
              iconUrl={agent?.icon_url}
              color={agent?.color}
              size={20}
              iconSize={11}
            />
          );
        }
        return (
          <div
            key={`${item.kind}-${
              item.kind === "subagent"
                ? item.slug
                : item.kind === "connector"
                ? item.name
                : item.agent_id
            }`}
          >
            {showHeader && (
              <div className={styles.mentionCategory}>{section}</div>
            )}
            <button
              type="button"
              className={`${styles.mentionItem} ${
                active ? styles.mentionItemActive : ""
              }`}
              onMouseEnter={() => onHover(idx)}
              onClick={() => onSelect(item)}
            >
              <span className={styles.mentionIcon}>{icon}</span>
              <span className={styles.mentionLabel}>{item.label}</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
