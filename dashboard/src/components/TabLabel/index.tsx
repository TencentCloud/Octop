import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import styles from "./index.module.less";

export const TAB_ICON_SIZE = 15;

interface TabLabelProps {
  icon: LucideIcon;
  children: ReactNode;
}

/** Tab title with a leading Lucide icon (admin advanced tab bar). */
export default function TabLabel({ icon: Icon, children }: TabLabelProps) {
  return (
    <span className={styles.tabLabel}>
      <span className={styles.tabIcon} aria-hidden="true">
        <Icon size={TAB_ICON_SIZE} />
      </span>
      {children}
    </span>
  );
}
