import { Tooltip } from "antd";
import {
  Archive,
  Box,
  CircleDashed,
  Database,
  Folder,
  HardDrive,
  Layers,
  Terminal,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BackendFlagIcon } from "./backendFlag";
import { backendFlagIcon, resolveBackendFlag } from "./backendFlag";
import { useNamedStorageBackends } from "./useNamedStorageBackends";
import styles from "../index.module.less";

interface BackendFlagProps {
  config: Record<string, unknown> | null | undefined;
  /**
   * Missing specs use the local-shell default. Peer experts do too: an
   * omitted backend is the same default on the other Octop.
   */
  assumeDefault?: boolean;
}

const FAMILY_ICON: Record<BackendFlagIcon, LucideIcon> = {
  shell: Terminal,
  filesystem: Folder,
  database: Database,
  storage: Archive,
  sandbox: Box,
  composite: Layers,
  state: CircleDashed,
  generic: HardDrive,
};

/**
 * One tinted line icon per backend family. The full name stays in the tooltip.
 */
export default function BackendFlag({
  config,
  assumeDefault = true,
}: BackendFlagProps) {
  const { t } = useTranslation();
  const backends = useNamedStorageBackends();
  const model = resolveBackendFlag(config?.backend, backends, {
    assumeDefault,
  });
  if (!model) return null;

  const label = model.labelText ?? (model.labelKey ? t(model.labelKey) : "");
  const kind = backendFlagIcon(model);
  const Icon = FAMILY_ICON[kind];

  return (
    <Tooltip title={label || undefined} mouseEnterDelay={0.3}>
      <span
        className={`${styles.backendFlag} ${
          styles[`backendFlag_${kind}`] ?? ""
        }`}
        role="img"
        aria-label={label}
      >
        <Icon size={13} strokeWidth={1.75} />
      </span>
    </Tooltip>
  );
}
