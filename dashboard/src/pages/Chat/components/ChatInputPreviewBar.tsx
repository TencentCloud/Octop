import { Image } from "antd";
import { X, FileText, Cpu } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuthImageSrc } from "../../../hooks/useAuthImageSrc";
import type { ChatAttachment } from "../hooks/useChat";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { KnowledgeBase } from "../../../api/modules/knowledgeBases";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import ExpertAgentAvatar from "./ExpertAgentAvatar";
import { ConnectorLogo } from "../../Agent/Connectors/connectorDefs";
import { knowledgeIconForName } from "../../KnowledgeBases/knowledgeIcons";
import { inferKindFromNameAndMime } from "../utils/chatAttachments";
import { ChatMediaPlayer } from "./ChatMediaPlayer";
import ContextChip from "./ContextChip";
import { skillChipIcon } from "../utils/skillChipIcon";
import { useSkillDisplayName } from "../../Agent/Skills/skillDisplayNames";
import { modelShortLabel } from "../../../utils/modelOptions";
import styles from "../index.module.less";

interface ChatInputPreviewBarProps {
  attachments: ChatAttachment[];
  uploading: boolean;
  selectedSkills: string[];
  selectedConnectors: string[];
  selectedKnowledgeBaseIds: string[];
  selectedTargetAgents: string[];
  selectedModel?: string | null;
  availableSkills?: SkillSpec[];
  availableConnectors?: {
    mcp_server_name: string;
    label: string;
    kind: string;
    default_open?: boolean;
  }[];
  availableKnowledgeBases?: KnowledgeBase[];
  availableAgents: ChatAgentOption[];
  onRemoveAttachment: (index: number) => void;
  onSkillsChange?: (names: string[]) => void;
  onConnectorsChange?: (names: string[]) => void;
  onKnowledgeBaseIdsChange?: (ids: string[]) => void;
  onTargetAgentsChange?: (ids: string[]) => void;
  onModelChange?: (model: string | null) => void;
}

function ComposerImagePreview({
  url,
  alt,
  className,
}: {
  url: string;
  alt: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const { src, loadState } = useAuthImageSrc(url, alt);

  if (loadState === "loading") {
    return (
      <div
        aria-hidden
        className={className}
        style={{ background: "var(--fn-bg-secondary)" }}
      />
    );
  }

  if (loadState === "error" || !src) {
    return (
      <div
        className={className}
        role="img"
        aria-label={alt || t("chat.imageLoadFailed")}
        style={{
          background: "#fff1f0",
          color: "#cf1322",
          fontSize: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: 4,
        }}
      >
        {t("chat.imageLoadFailed")}
      </div>
    );
  }

  return (
    <Image
      src={src}
      alt={alt}
      width={64}
      height={64}
      style={{ objectFit: "cover", display: "block" }}
      preview={{ mask: false }}
    />
  );
}

export default function ChatInputPreviewBar({
  attachments,
  uploading,
  selectedSkills,
  selectedConnectors,
  selectedKnowledgeBaseIds,
  selectedTargetAgents,
  availableSkills,
  availableConnectors,
  availableKnowledgeBases,
  availableAgents,
  onRemoveAttachment,
  onSkillsChange,
  onConnectorsChange,
  onKnowledgeBaseIdsChange,
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
    selectedKnowledgeBaseIds.length > 0 ||
    selectedSkills.length > 0 ||
    selectedTargetAgents.length > 0 ||
    showModelChip;

  if (!hasContent) return null;

  const imageAttachments = attachments.filter(
    (attachment) =>
      inferKindFromNameAndMime(
        attachment.mediaType,
        attachment.filename,
        attachment.kind,
      ) === "image",
  );

  return (
    <div className={styles.imagePreviewBar}>
      {imageAttachments.length > 0 ? (
        <Image.PreviewGroup>
          {attachments.map((attachment, idx) =>
            inferKindFromNameAndMime(
              attachment.mediaType,
              attachment.filename,
              attachment.kind,
            ) === "image" ? (
              <div
                key={`${attachment.url}-${idx}`}
                className={styles.imagePreviewItem}
              >
                <ComposerImagePreview
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
            ) : null,
          )}
        </Image.PreviewGroup>
      ) : null}
      {attachments.map((attachment, idx) => {
        const kind = inferKindFromNameAndMime(
          attachment.mediaType,
          attachment.filename,
          attachment.kind,
        );
        if (kind === "image") return null;
        if (kind === "video" || kind === "audio") {
          return (
            <div
              key={`${attachment.url}-${idx}`}
              className={
                kind === "video"
                  ? styles.composerMediaItem
                  : styles.attachmentPreviewCard
              }
            >
              <ChatMediaPlayer
                url={attachment.url}
                filename={attachment.filename}
                workspacePath={attachment.workspacePath}
                mediaType={attachment.mediaType}
                kind={kind}
                compact
              />
              <button
                className={styles.imagePreviewRemove}
                onClick={() => onRemoveAttachment(idx)}
                type="button"
              >
                <X size={12} />
              </button>
            </div>
          );
        }
        return (
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
        );
      })}
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
              icon={skillChipIcon(skill)}
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
      {availableKnowledgeBases &&
        onKnowledgeBaseIdsChange &&
        selectedKnowledgeBaseIds.map((id) => {
          const knowledgeBase = availableKnowledgeBases.find(
            (base) => base.id === id,
          );
          if (!knowledgeBase) return null;
          return (
            <ContextChip
              key={id}
              variant="knowledge"
              icon={knowledgeIconForName(knowledgeBase.icon_name, 12)}
              label={knowledgeBase.name}
              onRemove={() =>
                onKnowledgeBaseIdsChange(
                  selectedKnowledgeBaseIds.filter((baseId) => baseId !== id),
                )
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
                  iconUrl={a.icon_url}
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
