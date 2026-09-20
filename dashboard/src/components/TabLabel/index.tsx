import { isValidElement, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import styles from "./index.module.less";

export const TAB_ICON_SIZE = 15;

export type TabIcon = LucideIcon | ReactNode;

interface TabLabelProps {
  icon: TabIcon;
  children: ReactNode;
}

function renderTabIcon(icon: TabIcon): ReactNode {
  if (
    isValidElement(icon) ||
    typeof icon === "string" ||
    typeof icon === "number"
  ) {
    return icon;
  }
  if (icon == null || typeof icon === "boolean") {
    return null;
  }
  // Lucide icons are components (function or forwardRef object).
  const Icon = icon as LucideIcon;
  return <Icon size={TAB_ICON_SIZE} />;
}

/** Tab title with a leading Lucide icon or custom React node (e.g. brand SVG). */
export default function TabLabel({ icon, children }: TabLabelProps) {
  return (
    <span className={styles.tabLabel}>
      <span className={styles.tabIcon} aria-hidden="true">
        {renderTabIcon(icon)}
      </span>
      {children}
    </span>
  );
}
