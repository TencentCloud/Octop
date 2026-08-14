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
  /** Smaller read-only chips above user messages in history. */
  compact?: boolean;
}

export default function ContextChip({
  variant,
  icon,
  label,
  onRemove,
  compact = false,
}: ContextChipProps) {
  return (
    <div
      className={`${styles.contextChip} ${variantClass[variant]} ${
        compact ? styles.contextChipCompact : ""
      }`}
    >
      <span className={styles.contextChipIcon}>{icon}</span>
      <span className={styles.contextChipLabel}>{label}</span>
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
