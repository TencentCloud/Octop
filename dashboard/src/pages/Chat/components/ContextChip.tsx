import type { ReactNode } from "react";
import { X } from "lucide-react";
import styles from "../index.module.less";

export type ContextChipVariant =
  | "skill"
  | "connector"
  | "knowledge"
  | "expert"
  | "model";

const variantClass: Record<ContextChipVariant, string> = {
  skill: styles.contextChipSkill,
  connector: styles.contextChipConnector,
  knowledge: styles.contextChipKnowledge,
  expert: styles.contextChipExpert,
  model: styles.contextChipModel,
};

interface ContextChipProps {
  variant: ContextChipVariant;
  icon: ReactNode;
  label: string;
  onRemove?: () => void;
  onOpen?: () => void;
  openLabel?: string;
  /** Smaller read-only chips above user messages in history. */
  compact?: boolean;
}

export default function ContextChip({
  variant,
  icon,
  label,
  onRemove,
  onOpen,
  openLabel,
  compact = false,
}: ContextChipProps) {
  return (
    <div
      className={`${styles.contextChip} ${variantClass[variant]} ${
        compact ? styles.contextChipCompact : ""
      }`}
    >
      <span className={styles.contextChipIcon}>{icon}</span>
      {onOpen ? (
        <button
          type="button"
          className={`${styles.contextChipLabel} ${styles.contextChipOpen}`}
          onClick={onOpen}
          aria-label={openLabel ?? label}
          title={openLabel}
        >
          {label}
        </button>
      ) : (
        <span className={styles.contextChipLabel}>{label}</span>
      )}
      {onRemove ? (
        <button
          type="button"
          className={styles.contextChipRemove}
          onClick={onRemove}
          aria-label={label}
        >
          <X size={12} />
        </button>
      ) : null}
    </div>
  );
}
