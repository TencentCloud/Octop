import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import styles from "../index.module.less";

interface SessionGroupHeaderProps {
  /** Already-localized label (section name or project name). */
  title: string;
  count: number;
  /** Decorative marker, e.g. 📌 / 💬 / 📦. */
  icon?: ReactNode;
  /** Collapsible headers expose ``aria-expanded``; the rest are static. */
  collapsible?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
  /** Project group headers sit one level below their section header. */
  nested?: boolean;
}

/**
 * Shared header for the three session sections (📌 / 💬 / 📦) and for the
 * per-project group headers inside a section.
 */
export default function SessionGroupHeader({
  title,
  count,
  icon,
  collapsible = false,
  expanded = false,
  onToggle,
  nested = false,
}: SessionGroupHeaderProps) {
  const label = `${title} (${count})`;
  const className = `${styles.sessionItem} ${
    nested ? styles.sessionItemNested : ""
  }`;

  if (!collapsible) {
    return (
      <div className={className} style={{ cursor: "default" }}>
        {icon ? (
          <span className={styles.sessionIcon} aria-hidden>
            {icon}
          </span>
        ) : null}
        <span className={styles.sessionTitle}>{label}</span>
      </div>
    );
  }

  return (
    <button
      type="button"
      className={className}
      aria-expanded={expanded}
      onClick={onToggle}
      style={{
        width: "100%",
        border: "none",
        background: "transparent",
        textAlign: "left",
      }}
    >
      {icon ? (
        <span className={styles.sessionIcon} aria-hidden>
          {icon}
        </span>
      ) : null}
      <span className={styles.sessionTitle}>{label}</span>
      <ChevronDown
        size={14}
        aria-hidden
        style={{
          marginLeft: "auto",
          transition: "transform 0.15s ease",
          transform: expanded ? "rotate(0deg)" : "rotate(-90deg)",
        }}
      />
    </button>
  );
}
