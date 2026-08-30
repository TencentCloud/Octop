import { Popconfirm } from "antd";
import { FileCode2, Info, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillPackageSkill } from "../../api/types/skillPackage";
import skillStyles from "../Agent/Skills/index.module.less";

interface PackageSkillCardProps {
  skill: SkillPackageSkill;
  canMutate: boolean;
  onClick: () => void;
  onDelete?: () => void;
}

const DEFAULT_COLOR = "#8B5CF6";

export function PackageSkillCard({
  skill,
  canMutate,
  onClick,
  onDelete,
}: PackageSkillCardProps) {
  const { t } = useTranslation();
  const iconUrl = skill.icon_url || undefined;
  const emoji = skill.emoji;
  const displayName = skill.name;
  const displayDesc = skill.description || t("skills.noDescription");
  const iconBg = `${DEFAULT_COLOR}18`;

  return (
    <div
      className={skillStyles.skillCard}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
    >
      <div className={skillStyles.cardBody}>
        <div className={skillStyles.cardHeader}>
          <div
            className={skillStyles.iconWrapper}
            style={{
              color: DEFAULT_COLOR,
              backgroundColor: iconUrl ? "transparent" : iconBg,
            }}
          >
            {iconUrl ? (
              <img
                src={iconUrl}
                alt=""
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: "var(--fn-radius-md)",
                  objectFit: "cover",
                }}
              />
            ) : emoji ? (
              <span style={{ fontSize: 22, lineHeight: 1 }}>{emoji}</span>
            ) : (
              <FileCode2 size={22} strokeWidth={2} />
            )}
          </div>
          <div className={skillStyles.cardMeta}>
            <div className={skillStyles.cardTitle}>{displayName}</div>
            <div className={skillStyles.cardBadges}>
              <span className={skillStyles.builtinBadge}>{skill.slug}</span>
            </div>
          </div>
        </div>

        <div className={skillStyles.cardDesc} title={displayDesc}>
          {displayDesc}
        </div>

        <div className={skillStyles.cardFooter}>
          <button
            type="button"
            className={skillStyles.detailBtn}
            onClick={(e) => {
              e.stopPropagation();
              onClick();
            }}
          >
            <Info size={14} />
            {t("common.viewDetail")}
          </button>
          {canMutate && onDelete ? (
            <div className={skillStyles.footerActions}>
              <Popconfirm
                title={t("skillPackages.deleteSkillConfirm")}
                okText={t("common.delete")}
                cancelText={t("common.cancel")}
                okButtonProps={{ danger: true }}
                onConfirm={onDelete}
              >
                <button
                  type="button"
                  className={skillStyles.deleteIconBtn}
                  onClick={(e) => e.stopPropagation()}
                  aria-label={t("common.delete")}
                >
                  <Trash2 size={14} />
                </button>
              </Popconfirm>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
