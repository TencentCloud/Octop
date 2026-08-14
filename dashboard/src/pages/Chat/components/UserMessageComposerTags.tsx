import { useMemo, type ReactNode } from "react";
import { Cpu } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UserComposerContext } from "../hooks/useChat";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { KnowledgeBase } from "../../../api/modules/knowledgeBases";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import ExpertAgentAvatar from "./ExpertAgentAvatar";
import { ConnectorLogo } from "../../Agent/Connectors/connectorDefs";
import { knowledgeIconForName } from "../../KnowledgeBases/knowledgeIcons";
import ContextChip, { type ContextChipVariant } from "./ContextChip";
import { skillChipLabel } from "../utils/skillChipLabel";
import { modelShortLabel } from "../../../utils/modelOptions";
import styles from "../index.module.less";

export interface ComposerTagLookups {
  skills?: SkillSpec[];
  connectors?: { mcp_server_name: string; label: string; kind: string }[];
  knowledgeBases?: KnowledgeBase[];
  agents?: ChatAgentOption[];
}

interface UserMessageComposerTagsProps {
  context?: UserComposerContext;
  lookups?: ComposerTagLookups;
}

export default function UserMessageComposerTags({
  context,
  lookups,
}: UserMessageComposerTagsProps) {
  const { t } = useTranslation();

  const tags = useMemo(() => {
    if (!context) return [];

    const items: Array<{
      key: string;
      variant: ContextChipVariant;
      icon: ReactNode;
      label: string;
    }> = [];

    for (const slug of context.skills ?? []) {
      const skill = lookups?.skills?.find((s) => s.slug === slug);
      items.push({
        key: `skill-${slug}`,
        variant: "skill",
        icon: skill ? skillChipLabel(skill) : "✦",
        label: skill?.name || slug,
      });
    }

    for (const name of context.connectors ?? []) {
      const connector = lookups?.connectors?.find(
        (c) => c.mcp_server_name === name,
      );
      items.push({
        key: `connector-${name}`,
        variant: "connector",
        icon: connector ? (
          <ConnectorLogo kind={connector.kind} size={14} />
        ) : (
          "⛓"
        ),
        label: connector?.label || name,
      });
    }

    for (const id of context.knowledgeBaseIds ?? []) {
      const knowledgeBase = lookups?.knowledgeBases?.find(
        (base) => base.id === id,
      );
      items.push({
        key: `knowledge-${id}`,
        variant: "knowledge",
        icon: knowledgeIconForName(knowledgeBase?.icon_name, 11),
        label: knowledgeBase?.name || id,
      });
    }

    for (const id of context.targetAgents ?? []) {
      const agent = lookups?.agents?.find((a) => a.agent_id === id);
      items.push({
        key: `agent-${id}`,
        variant: "expert",
        icon: (
          <ExpertAgentAvatar
            iconName={agent?.icon_name}
            color={agent?.color}
            size={16}
            iconSize={9}
            muted
          />
        ),
        label: agent?.name || id,
      });
    }

    if (context.model) {
      items.push({
        key: `model-${context.model}`,
        variant: "model",
        icon: <Cpu size={11} strokeWidth={2.2} aria-hidden />,
        label: modelShortLabel(context.model),
      });
    }

    return items;
  }, [context, lookups]);

  if (tags.length === 0) return null;

  return (
    <div
      className={styles.userComposerTags}
      aria-label={t("chat.composerContextLabel")}
    >
      {tags.map((tag) => (
        <ContextChip
          key={tag.key}
          variant={tag.variant}
          icon={tag.icon}
          label={tag.label}
          compact
        />
      ))}
    </div>
  );
}
