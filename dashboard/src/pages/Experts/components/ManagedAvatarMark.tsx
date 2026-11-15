import type { ReactNode } from "react";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import cx from "classnames";

import {
  isBuiltinRunner,
  runnerIcon,
  runnerLabelKey,
} from "../../Agent/ACP/constants";
import styles from "../index.module.less";

export function managedRunnerId(
  agent?: {
    kind?: string | null;
    config?: Record<string, unknown> | null;
  } | null,
): string | null {
  if (agent?.kind !== "managed") return null;
  const runner = agent.config?.managed_runner;
  return typeof runner === "string" && runner.trim() ? runner.trim() : null;
}

/** Avatar with the bound ACP runner's icon at the bottom-right. */
export function ManagedAvatarMark({
  runner,
  children,
}: {
  runner?: string | null;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const id = (runner || "").trim();
  if (!id) return children;
  const label = isBuiltinRunner(id) ? t(runnerLabelKey(id)) : id;
  return (
    <span className={styles.avatarWithMark}>
      {children}
      <Tooltip title={label} mouseEnterDelay={0.3}>
        <span className={styles.managedMark} aria-label={label}>
          <img
            src={runnerIcon(id)}
            alt=""
            className={cx(id === "pi" && styles.invertOnDark)}
          />
        </span>
      </Tooltip>
    </span>
  );
}
