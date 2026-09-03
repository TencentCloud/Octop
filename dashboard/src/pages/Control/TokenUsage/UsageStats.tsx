import { useEffect, useRef, useState } from "react";
import { Popover } from "antd";
import { MoreVertical } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "./index.module.less";

export interface UsageStatItem {
  key: string;
  label: string;
  value: string | number;
}

const STAT_CARD_MIN_PX = 160;
const STAT_GAP_PX = 12;
const STAT_MORE_PX = 36;

/** How many metric cards fit in a single row, reserving the ⋮ when needed. */
export function visibleStatCount(width: number, total: number): number {
  if (total <= 0) return 0;
  const maxFit = Math.floor(
    (width + STAT_GAP_PX) / (STAT_CARD_MIN_PX + STAT_GAP_PX),
  );
  if (maxFit >= total) return total;
  const withMore = Math.floor(
    (width - STAT_MORE_PX) / (STAT_CARD_MIN_PX + STAT_GAP_PX),
  );
  return Math.max(1, Math.min(total - 1, withMore));
}

function StatBlock({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className={styles.statBlock}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value}</div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className={styles.statsDrawerRow}>
      <span className={styles.statsDrawerLabel}>{label}</span>
      <span className={styles.statsDrawerValue}>{value}</span>
    </div>
  );
}

export function UsageStats({
  items,
  width: widthProp,
  overflowEnabled = true,
}: {
  items: UsageStatItem[];
  width?: number;
  /** Desktop-only: hide overflowing cards behind ⋮. Off on phones. */
  overflowEnabled?: boolean;
}) {
  const { t } = useTranslation();
  const hostRef = useRef<HTMLDivElement>(null);
  const [measuredWidth, setMeasuredWidth] = useState<number | null>(null);

  useEffect(() => {
    if (widthProp !== undefined || !overflowEnabled) return;
    const el = hostRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const apply = (width: number) => {
      if (width > 0) setMeasuredWidth(width);
    };
    apply(el.clientWidth);
    const ro = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width === undefined) return;
      apply(width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [widthProp, overflowEnabled]);

  const width = widthProp ?? measuredWidth ?? Number.POSITIVE_INFINITY;
  const visible = overflowEnabled
    ? visibleStatCount(width, items.length)
    : items.length;
  const shown = items.slice(0, visible);
  const overflow = overflowEnabled ? items.slice(visible) : [];

  return (
    <div ref={hostRef} className={styles.statsHost}>
      <div className={styles.statsRow}>
        <div
          className={
            overflowEnabled ? styles.statsGrid : styles.statsGridMobile
          }
          style={
            overflowEnabled
              ? {
                  gridTemplateColumns: `repeat(${Math.max(
                    shown.length,
                    1,
                  )}, minmax(160px, 1fr))`,
                }
              : undefined
          }
        >
          {shown.map((item) => (
            <StatBlock key={item.key} label={item.label} value={item.value} />
          ))}
        </div>
        {overflow.length > 0 ? (
          <Popover
            trigger="click"
            placement="bottomRight"
            content={
              <div className={styles.statsDrawerList}>
                {overflow.map((item) => (
                  <StatRow
                    key={item.key}
                    label={item.label}
                    value={item.value}
                  />
                ))}
              </div>
            }
          >
            <button
              type="button"
              className={styles.statsMoreIcon}
              aria-label={t("common.viewMore")}
            >
              <MoreVertical size={18} strokeWidth={2} aria-hidden />
            </button>
          </Popover>
        ) : null}
      </div>
    </div>
  );
}
