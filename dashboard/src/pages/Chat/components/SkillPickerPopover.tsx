import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Import } from "lucide-react";
import SearchablePickerPanel, {
  pickerStyles,
} from "../../../components/ChatPicker/SearchablePickerPanel";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import { useSkillDisplayName } from "../../Agent/Skills/skillDisplayNames";
import styles from "../index.module.less";

interface SkillPickerPopoverProps {
  skills: SkillSpec[];
  selectedSkills: string[];
  onSkillsChange: (names: string[]) => void;
  onNavigateAway?: () => void;
}

function SkillAvatar({ skill }: { skill: SkillSpec }) {
  const iconUrl = skill.iconUrl?.trim();
  return (
    <span className={styles.skillPickerAvatar}>
      {iconUrl ? (
        <img src={iconUrl} alt="" className={styles.skillPickerAvatarImg} />
      ) : (
        skillAvatarFallback(skill)
      )}
    </span>
  );
}

function skillAvatarFallback(skill: SkillSpec): string {
  if (skill.emoji) return skill.emoji;
  const name = skill.name || skill.slug;
  return name.charAt(0).toUpperCase();
}

export default function SkillPickerPopover({
  skills,
  selectedSkills,
  onSkillsChange,
  onNavigateAway,
}: SkillPickerPopoverProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const skillDisplayName = useSkillDisplayName();

  const enabledSkills = useMemo(
    () => skills.filter((s) => s.enabled),
    [skills],
  );

  const filterFn = useCallback(
    (skill: SkillSpec, query: string) => {
      const label = skillDisplayName(skill);
      return (
        label.toLowerCase().includes(query) ||
        skill.name.toLowerCase().includes(query) ||
        skill.slug.toLowerCase().includes(query) ||
        (skill.description || "").toLowerCase().includes(query)
      );
    },
    [skillDisplayName],
  );

  return (
    <SearchablePickerPanel
      items={enabledSkills}
      filterFn={filterFn}
      searchPlaceholder={t("chat.skillPickerSearch")}
      emptyMessage={t("chat.skillPickerEmpty")}
      width="wide"
      footerIcon={<Import size={15} aria-hidden />}
      footerLabel={t("skills.importSkills")}
      onFooterClick={() => {
        onNavigateAway?.();
        navigate("/personalization/skills");
      }}
      renderItem={(skill) => {
        const active = selectedSkills.includes(skill.slug);
        return (
          <button
            key={skill.slug}
            type="button"
            className={`${styles.skillPickerItem} ${
              active ? styles.skillPickerItemActive : ""
            }`}
            onClick={() => {
              const next = active
                ? selectedSkills.filter((n) => n !== skill.slug)
                : [...selectedSkills, skill.slug];
              onSkillsChange(next);
            }}
          >
            <SkillAvatar skill={skill} />
            <span className={pickerStyles.itemText}>
              <span className={pickerStyles.itemName}>
                {skillDisplayName(skill)}
              </span>
              {skill.description ? (
                <span className={pickerStyles.itemDesc}>
                  {skill.description}
                </span>
              ) : null}
            </span>
          </button>
        );
      }}
    />
  );
}
