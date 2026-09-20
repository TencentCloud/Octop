import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { isKnownPluginGroup } from "./pluginGroups";
import styles from "./index.module.less";

function groupLabel(
  group: string | null | undefined,
  t: (key: string) => string,
): string | null {
  const slug = (group || "").trim().toLowerCase();
  if (!slug) return null;
  return isKnownPluginGroup(slug)
    ? t(`plugins.groups.${slug}`)
    : t("plugins.groupUnknown");
}

/** Quiet meta line: kind · group · version (no chunky Tags). */
export function PluginCardMeta({
  kind,
  group,
  version,
  trailing,
}: {
  kind?: string | null;
  group?: string | null;
  version?: string | null;
  trailing?: ReactNode;
}) {
  const { t } = useTranslation();
  const parts: string[] = [];
  if (kind?.trim()) parts.push(kind.trim());
  const g = groupLabel(group, t);
  if (g) parts.push(g);
  if (version?.trim()) parts.push(`v${version.trim()}`);

  if (parts.length === 0 && !trailing) return null;

  return (
    <div className={styles.cardMetaRow}>
      {parts.length > 0 ? (
        <div className={styles.cardMeta}>
          {parts.map((part, index) => (
            <span key={`${part}-${index}`}>
              {index > 0 ? (
                <span className={styles.cardMetaSep} aria-hidden>
                  ·
                </span>
              ) : null}
              <span className={styles.cardMetaItem}>{part}</span>
            </span>
          ))}
        </div>
      ) : null}
      {trailing ? <div className={styles.cardChips}>{trailing}</div> : null}
    </div>
  );
}
