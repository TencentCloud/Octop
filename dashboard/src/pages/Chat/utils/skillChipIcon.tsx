import type { ReactNode } from "react";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import styles from "../index.module.less";

function skillChipFallback(skill: SkillSpec): string {
  if (skill.emoji) return skill.emoji;
  const name = skill.name || skill.slug;
  return name.charAt(0).toUpperCase();
}

/** Composer / history chip icon: market image, then emoji, then initial. */
export function skillChipIcon(skill: SkillSpec): ReactNode {
  const iconUrl = skill.iconUrl?.trim();
  if (iconUrl) {
    return <img src={iconUrl} alt="" className={styles.contextChipIconImg} />;
  }
  return skillChipFallback(skill);
}
