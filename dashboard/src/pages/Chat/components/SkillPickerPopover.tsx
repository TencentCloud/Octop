import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Check, Import } from "lucide-react";
import SearchablePickerPanel, {
  pickerStyles,
} from "../../../components/ChatPicker/SearchablePickerPanel";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import {
  resolveSkillDisplayName,
  useSkillDisplayName,
} from "../../Agent/Skills/skillDisplayNames";
import styles from "../index.module.less";

interface SkillPickerPopoverProps {
  skills: SkillSpec[];
  /** Skill ``/slug`` tokens currently in the composer. */
  activeSlugs?: readonly string[] | null;
  onSelectSkill: (slug: string) => void;
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
  const name = resolveSkillDisplayName(skill);
  return name.charAt(0).toUpperCase();
}

export default function SkillPickerPopover({
  skills,
  activeSlugs = null,
  onSelectSkill,
  onNavigateAway,
}: SkillPickerPopoverProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const skillDisplayName = useSkillDisplayName();
  const activeSet = useMemo(() => {
    const set = new Set<string>();
    for (const slug of activeSlugs ?? []) {
      const normalized = slug.trim().toLowerCase();
      if (normalized) set.add(normalized);
    }
    return set;
  }, [activeSlugs]);

  const enabledSkills = useMemo(
    () => skills.filter((s) => s.enabled),
    [skills],
  );

  const filterFn = useCallback(
    (skill: SkillSpec, query: string) => {
      const label = skillDisplayName(skill);
      const q = query.toLowerCase();
      return (
        label.toLowerCase().includes(q) ||
        skill.name.toLowerCase().includes(q) ||
        skill.slug.toLowerCase().includes(q) ||
        (skill.description || "").toLowerCase().includes(q)
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
        const label = skillDisplayName(skill);
        const active = activeSet.has(skill.slug.toLowerCase());
        return (
          <button
            key={skill.slug}
            type="button"
            className={`${styles.skillPickerItem} ${
              active ? styles.skillPickerItemActive : ""
            }`}
            aria-pressed={active}
            onClick={() => {
              onSelectSkill(skill.slug);
              onNavigateAway?.();
            }}
          >
            <SkillAvatar skill={skill} />
            <span className={pickerStyles.itemText}>
              <span className={pickerStyles.itemName}>{label}</span>
              {skill.description ? (
                <span className={pickerStyles.itemDesc}>
                  {skill.description}
                </span>
              ) : null}
            </span>
            {active ? (
              <Check
                size={16}
                className={styles.skillPickerCheck}
                aria-hidden
              />
            ) : null}
          </button>
        );
      }}
    />
  );
}
