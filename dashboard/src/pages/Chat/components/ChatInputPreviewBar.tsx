import { X, FileText, Cpu } from "lucide-react";
import AuthImage from "../../../components/AuthImage";
import type { ChatAttachment } from "../hooks/useChat";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import ExpertAgentAvatar from "./ExpertAgentAvatar";
import { ConnectorLogo } from "../../Agent/Connectors/connectorDefs";
import ContextChip from "./ContextChip";
import { skillChipLabel } from "../utils/skillChipLabel";
import { useSkillDisplayName } from "../../Agent/Skills/skillDisplayNames";
import { modelShortLabel } from "../../../utils/modelOptions";
import styles from "../index.module.less";

interface ChatInputPreviewBarProps {
  attachments: ChatAttachment[];
  uploading: boolean;
  selectedSkills: string[];
  selectedConnectors: string[];
  selectedTargetAgents: string[];
  selectedModel?: string | null;
  availableSkills?: SkillSpec[];
  availableConnectors?: {
    mcp_server_name: string;
    label: string;
    kind: string;
  }[];
  availableAgents: ChatAgentOption[];
  onRemoveAttachment: (index: number) => void;
  onSkillsChange?: (names: string[]) => void;
  onConnectorsChange?: (names: string[]) => void;
  onTargetAgentsChange?: (ids: string[]) => void;
  onModelChange?: (model: string | null) => void;
}

export default function ChatInputPreviewBar({
  attachments,
  uploading,
  selectedSkills,
  selectedConnectors,
  selectedTargetAgents,
  availableSkills,
  availableConnectors,
  availableAgents,
  onRemoveAttachment,
  onSkillsChange,
  onConnectorsChange,
  onTargetAgentsChange,
  selectedModel,
  onModelChange,
}: ChatInputPreviewBarProps) {
  const skillDisplayName = useSkillDisplayName();
  // Show the chip whenever a model is explicitly selected, mirroring how
  // skills / experts / connectors behave — not only when it differs from the
  // agent default (that was the old "override" behavior).
  const selectedModelValue = (selectedModel || "").trim();
  const showModelChip = selectedModelValue.length > 0 && !!onModelChange;

  const hasContent =
    attachments.length > 0 ||
    uploading ||
    selectedConnectors.length > 0 ||
    selectedSkills.length > 0 ||
    selectedTargetAgents.length > 0 ||
    showModelChip;

  if (!hasContent) return null;

  return (
    <div className={styles.imagePreviewBar}>
      {attachments.map((attachment, idx) =>
        attachment.kind === "image" ? (
          <div
            key={`${attachment.url}-${idx}`}
            className={styles.imagePreviewItem}
          >
            <AuthImage
              url={attachment.url}
              alt={attachment.filename || "preview"}
              className={styles.imagePreviewThumb}
            />
            <button
              className={styles.imagePreviewRemove}
              onClick={() => onRemoveAttachment(idx)}
              type="button"
            >
              <X size={12} />
            </button>
          </div>
        ) : (
          <div
            key={`${attachment.url}-${idx}`}
            className={styles.attachmentPreviewCard}
          >
            <div className={styles.attachmentPreviewMeta}>
              <FileText size={14} className={styles.attachmentPreviewIcon} />
              <span className={styles.attachmentPreviewName}>
                {attachment.filename || attachment.url}
              </span>
            </div>
            <button
              className={styles.imagePreviewRemove}
              onClick={() => onRemoveAttachment(idx)}
              type="button"
            >
              <X size={12} />
            </button>
          </div>
        ),
      )}
      {uploading && (
        <div className={styles.imagePreviewItem}>
          <div className={styles.imagePreviewLoading}>
            <div className={styles.uploadSpinner} />
          </div>
        </div>
      )}
      {availableSkills &&
        onSkillsChange &&
        selectedSkills.map((slug) => {
          const skill = availableSkills.find((s) => s.slug === slug);
          if (!skill) return null;
          return (
            <ContextChip
              key={slug}
              variant="skill"
              icon={skillChipLabel(skill)}
              label={skillDisplayName(skill)}
              onRemove={() =>
                onSkillsChange(selectedSkills.filter((n) => n !== slug))
              }
            />
          );
        })}
      {availableConnectors &&
        onConnectorsChange &&
        selectedConnectors.map((name) => {
          const c = availableConnectors.find((x) => x.mcp_server_name === name);
          if (!c) return null;
          return (
            <ContextChip
              key={name}
              variant="connector"
              icon={<ConnectorLogo kind={c.kind} size={16} />}
              label={c.label}
              onRemove={() =>
                onConnectorsChange(selectedConnectors.filter((n) => n !== name))
              }
            />
          );
        })}
      {onTargetAgentsChange &&
        selectedTargetAgents.map((id) => {
          const a = availableAgents.find((x) => x.agent_id === id);
          if (!a) return null;
          return (
            <ContextChip
              key={id}
              variant="expert"
              icon={
                <ExpertAgentAvatar
                  iconName={a.icon_name}
                  color={a.color}
                  size={18}
                  iconSize={10}
                />
              }
              label={a.name}
              onRemove={() =>
                onTargetAgentsChange(
                  selectedTargetAgents.filter((x) => x !== id),
                )
              }
            />
          );
        })}
      {showModelChip && (
        <ContextChip
          variant="model"
          icon={<Cpu size={12} strokeWidth={2.2} aria-hidden />}
          label={modelShortLabel(selectedModelValue)}
          onRemove={() => onModelChange?.(null)}
        />
      )}
    </div>
  );
}
