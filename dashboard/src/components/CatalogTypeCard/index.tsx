import { memo, type CSSProperties, type ReactNode } from "react";
import styles from "./catalogTypeCard.module.less";

export interface CatalogTypeCardProps {
  accent: string;
  title: string;
  description: string;
  icon: ReactNode;
  hint?: string;
  /** Optional chip shown under the title (e.g. a category label). */
  tag?: ReactNode;
  configuredBadge?: ReactNode;
  disabled?: boolean;
  onClick: () => void;
}

export const CatalogTypeCard = memo(function CatalogTypeCard({
  accent,
  title,
  description,
  icon,
  hint,
  tag,
  configuredBadge,
  disabled = false,
  onClick,
}: CatalogTypeCardProps) {
  const cardClass = disabled ? styles.cardDisabled : styles.card;

  return (
    <div
      className={cardClass}
      style={{ "--catalog-accent": accent } as CSSProperties}
      onClick={() => !disabled && onClick()}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) => e.key === "Enter" && !disabled && onClick()}
    >
      {configuredBadge}

      <div className={styles.header}>
        <div
          className={styles.icon}
          style={{ color: accent, background: `${accent}18` }}
        >
          {icon}
        </div>
        <div className={styles.titleCol}>
          <div className={styles.title}>{title}</div>
          {tag}
        </div>
      </div>

      <div className={styles.description}>{description}</div>

      {hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
});
