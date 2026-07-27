import {
  Archive,
  Code2,
  FileSpreadsheet,
  FileText,
  Image,
  Info,
  Presentation,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillSpec } from "../useSkills";
import { useSkillDisplayName } from "../skillDisplayNames";
import styles from "../index.module.less";

/** SkillHub metadata matched by slug — used to show the marketplace's
 * Chinese name / description / icon for installed skills (falls back to the
 * local SKILL.md values when absent). */
export interface SkillHubInfo {
  name?: string;
  description_zh?: string;
  iconUrl?: string | null;
}

interface SkillCardProps {
  skill: SkillSpec;
  hubInfo?: SkillHubInfo;
  isHover: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onToggleEnabled: (e: React.MouseEvent) => void;
  onDelete?: (e?: React.MouseEvent) => void;
}

/**
 * Brand colour used as the icon tint when a skill doesn't bring its own
 * emoji or kind hint. Customised skills always render the gradient
 * Sparkles icon.
 */
const DEFAULT_COLOR = "#8B5CF6";

const FILE_ICON_SIZE = 16;

const getFileIcon = (filePath: string) => {
  const extension = filePath.split(".").pop()?.toLowerCase() || "";
  switch (extension) {
    case "txt":
    case "md":
    case "markdown":
      return (
        <FileText
          size={FILE_ICON_SIZE}
          color="var(--fn-color-info)"
          strokeWidth={2}
        />
      );
    case "zip":
    case "rar":
    case "7z":
    case "tar":
    case "gz":
      return (
        <Archive
          size={FILE_ICON_SIZE}
          color="var(--fn-color-file-zip)"
          strokeWidth={2}
        />
      );
    case "pdf":
      return (
        <FileText
          size={FILE_ICON_SIZE}
          color="var(--fn-color-danger)"
          strokeWidth={2}
        />
      );
    case "doc":
    case "docx":
      return (
        <FileText
          size={FILE_ICON_SIZE}
          color="var(--fn-color-file-word)"
          strokeWidth={2}
        />
      );
    case "xls":
    case "xlsx":
      return (
        <FileSpreadsheet
          size={FILE_ICON_SIZE}
          color="var(--fn-color-success)"
          strokeWidth={2}
        />
      );
    case "ppt":
    case "pptx":
      return (
        <Presentation
          size={FILE_ICON_SIZE}
          color="var(--fn-color-file-ppt)"
          strokeWidth={2}
        />
      );
    case "jpg":
    case "jpeg":
    case "png":
    case "gif":
    case "svg":
    case "webp":
      return (
        <Image
          size={FILE_ICON_SIZE}
          color="var(--fn-color-file-image)"
          strokeWidth={2}
        />
      );
    case "py":
    case "js":
    case "ts":
    case "jsx":
    case "tsx":
    case "java":
    case "cpp":
    case "c":
    case "go":
    case "rs":
    case "rb":
    case "php":
      return (
        <Code2
          size={FILE_ICON_SIZE}
          color="var(--fn-color-success)"
          strokeWidth={2}
        />
      );
    default:
      return (
        <FileText
          size={FILE_ICON_SIZE}
          color="var(--fn-color-info)"
          strokeWidth={2}
        />
      );
  }
};

const CustomizedSkillIcon = () => (
  <svg width="0" height="0" style={{ position: "absolute" }}>
    <defs>
      <linearGradient
        id="customSkillGradient"
        x1="0%"
        y1="0%"
        x2="100%"
        y2="100%"
      >
        <stop offset="0%" stopColor="#8B5CF6" />
        <stop offset="100%" stopColor="#F59E0B" />
      </linearGradient>
    </defs>
  </svg>
);

const renderSkillIcon = (skill: SkillSpec) => {
  // Frontmatter emoji wins — agents can override the icon by editing
  // SKILL.md without the dashboard caring.
  if (skill.emoji) {
    return <span style={{ fontSize: 22, lineHeight: 1 }}>{skill.emoji}</span>;
  }
  // For now every octop skill is workspace-kind — show the gradient
  // sparkles to differentiate user-created skills visually.
  if (skill.kind === "workspace") {
    return (
      <>
        <CustomizedSkillIcon />
        <Sparkles size={22} style={{ stroke: "url(#customSkillGradient)" }} />
      </>
    );
  }
  return getFileIcon(skill.slug);
};

export function SkillCard({
  skill,
  hubInfo,
  onClick,
  onMouseEnter,
  onMouseLeave,
  onToggleEnabled,
  onDelete,
}: SkillCardProps) {
  const { t } = useTranslation();
  const skillDisplayName = useSkillDisplayName();
  const isBuiltin = skill.kind === "builtin";
  const isCustomized = skill.kind === "workspace";
  const iconColor = DEFAULT_COLOR;
  const iconBg = `${iconColor}18`; // ~10% opacity tint

  // Prefer the SkillHub marketplace's Chinese name / description / icon when
  // this installed skill matches a hub skill by slug; fall back to SKILL.md.
  const displayName = hubInfo?.name || skillDisplayName(skill);
  const displayDesc = hubInfo?.description_zh || skill.description;
  const hubIcon = hubInfo?.iconUrl || skill.iconUrl;

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!skill.enabled && onDelete) {
      onDelete(e);
    }
  };

  return (
    <div
      className={styles.skillCard}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
    >
      <div className={styles.cardBody}>
        <div className={styles.cardHeader}>
          <div
            className={styles.iconWrapper}
            style={{
              color: iconColor,
              backgroundColor: hubIcon ? "transparent" : iconBg,
            }}
          >
            {hubIcon ? (
              <img
                src={hubIcon}
                alt=""
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: "var(--fn-radius-md)",
                  objectFit: "cover",
                }}
              />
            ) : (
              renderSkillIcon(skill)
            )}
          </div>
          <div className={styles.cardMeta}>
            <div className={styles.cardTitle}>{displayName}</div>
            <div className={styles.cardBadges}>
              {isBuiltin && (
                <span className={styles.builtinBadge}>
                  {t("skills.kindBuiltin")}
                </span>
              )}
              {skill.enabled && (
                <span className={styles.enabledBadge}>
                  ✓ {t("common.enabled")}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className={styles.cardDesc} title={displayDesc || undefined}>
          {displayDesc || t("skills.noDescription")}
        </div>

        <div className={styles.cardFooter}>
          <button
            type="button"
            className={styles.detailBtn}
            onClick={(e) => {
              e.stopPropagation();
              onClick();
            }}
          >
            <Info size={14} />
            {t("common.viewDetail")}
          </button>

          <div className={styles.footerActions}>
            {isCustomized && onDelete && (
              <button
                type="button"
                className={styles.deleteIconBtn}
                onClick={handleDeleteClick}
                disabled={skill.enabled}
                aria-label={t("common.delete")}
                title={
                  skill.enabled
                    ? t("skills.disableBeforeDelete")
                    : (t("common.delete") as string)
                }
              >
                <Trash2 size={14} />
              </button>
            )}
            <button
              type="button"
              className={`${styles.applyBtn} ${
                skill.enabled ? styles.appliedBtn : styles.applyActiveBtn
              }`}
              onClick={(e) => {
                e.stopPropagation();
                onToggleEnabled(e);
              }}
            >
              {skill.enabled ? t("common.disable") : t("skills.applyNow")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
