import { Button } from "antd";
import { Inbox, AlertCircle } from "lucide-react";
import type { ReactNode } from "react";
import { OctopEmptyMascot } from "./OctopEmptyMascot";

interface EmptyStateProps {
  /** Icon element. Overrides the default for the current variant. */
  icon?: ReactNode;
  /** Main title */
  title?: string;
  /** Descriptive subtitle */
  description?: string;
  /** Optional action button text */
  actionLabel?: string;
  /** Optional action button callback */
  onAction?: () => void;
  /**
   * Visual variant:
   * - empty: inbox icon
   * - error: alert icon
   * - mascot: shared Octop empty mascot (prefer for list/detail empty shells)
   */
  variant?: "empty" | "error" | "mascot";
  className?: string;
}

/**
 * Generic empty/error state placeholder for list and table pages.
 * Provides a consistent visual treatment across the app.
 */
export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  variant = "empty",
  className,
}: EmptyStateProps) {
  const defaultIcon =
    variant === "error" ? (
      <AlertCircle
        size={40}
        strokeWidth={1.2}
        style={{ color: "var(--fn-color-danger)" }}
      />
    ) : variant === "mascot" ? (
      <OctopEmptyMascot />
    ) : (
      <Inbox
        size={40}
        strokeWidth={1.2}
        style={{ color: "var(--fn-text-quaternary, #bfbfbf)" }}
      />
    );

  return (
    <div
      className={className}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
        gap: 8,
        textAlign: "center",
      }}
    >
      <div style={{ marginBottom: 8 }}>{icon ?? defaultIcon}</div>
      {title && (
        <div
          style={{
            fontSize: 15,
            fontWeight: 500,
            color: "var(--fn-text-primary)",
          }}
        >
          {title}
        </div>
      )}
      {description && (
        <div
          style={{
            fontSize: 13,
            color: "var(--fn-text-tertiary)",
            maxWidth: 320,
            lineHeight: 1.6,
          }}
        >
          {description}
        </div>
      )}
      {actionLabel && onAction && (
        <Button type="primary" onClick={onAction} style={{ marginTop: 12 }}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}

export { OctopEmptyMascot } from "./OctopEmptyMascot";
export { OCTOP_EMPTY_MASCOT_SRC } from "../../assets/mascot";
