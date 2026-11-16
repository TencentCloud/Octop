import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "antd";

import styles from "./MetricHeatmap.module.less";

export type MetricPoint = { t: number; v: number };

/** Terminal-style amber ramp (0 = idle, 4 = hot), themed via CSS vars. */
const LEVEL_COLORS = [
  "var(--sc-heat-0)",
  "var(--sc-heat-1)",
  "var(--sc-heat-2)",
  "var(--sc-heat-3)",
  "var(--sc-heat-4)",
];

const GAP = 3;
const MIN_CELL = 10;
const MAX_CELL = 18;

function levelOf(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 20) return 0;
  if (value < 40) return 1;
  if (value < 60) return 2;
  if (value < 80) return 3;
  return 4;
}

/**
 * 热力条：格子等宽、每行刚好铺满，装不下就换行。
 *
 * 格子宽度由容器实测宽度反推（而不是交给 flex 拉伸），这样最后一行只有
 * 几个格子时也不会被拉宽，行与行之间始终对齐。
 */
export default function MetricHeatmap({
  points,
  unit = "%",
  selectedT = null,
  onSelect,
}: {
  points: MetricPoint[];
  unit?: string;
  selectedT?: number | null;
  onSelect?: (t: number) => void;
}) {
  const { t } = useTranslation();
  const stripRef = useRef<HTMLDivElement>(null);
  const [cellWidth, setCellWidth] = useState(12);

  const cells = useMemo(
    () =>
      points
        .filter((point) => Number.isFinite(point.v))
        .map((point) => {
          const date = new Date(point.t * 1000);
          const time = date.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          });
          return {
            ...point,
            level: levelOf(point.v),
            time,
            label: `${date.toLocaleDateString()} ${time}`,
          };
        }),
    [points],
  );

  useEffect(() => {
    const element = stripRef.current;
    if (!element) return;

    const measure = () => {
      const width = element.clientWidth;
      if (!width) return;
      // 每行最多能放几个格子（按最小宽度算），不能超过实际采样点数
      const perRow = Math.max(
        1,
        Math.min(
          Math.floor((width + GAP) / (MIN_CELL + GAP)),
          cells.length || 1,
        ),
      );
      const next = (width - GAP * (perRow - 1)) / perRow;
      setCellWidth(Math.min(MAX_CELL, Math.max(MIN_CELL, next)));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [cells.length]);

  if (!cells.length) {
    return (
      <div className={styles.empty}>
        {t("cloud.heatmapEmpty", "暂无足够的监控数据生成热力图")}
      </div>
    );
  }

  const first = cells[0];
  const middle = cells[Math.floor(cells.length / 2)];
  const last = cells[cells.length - 1];

  return (
    <div className={styles.wrap}>
      <div className={styles.strip} ref={stripRef}>
        {cells.map((cell) => (
          <Tooltip
            key={cell.t}
            title={`${cell.label} · ${cell.v.toFixed(1)}${unit}`}
          >
            <span
              role="button"
              tabIndex={-1}
              aria-label={`${cell.label} ${cell.v.toFixed(1)}${unit}`}
              className={
                cell.t === selectedT
                  ? `${styles.cell} ${styles.cellActive}`
                  : styles.cell
              }
              style={{
                width: `${cellWidth}px`,
                background: LEVEL_COLORS[cell.level],
              }}
              onClick={() => onSelect?.(cell.t)}
            />
          </Tooltip>
        ))}
      </div>
      <div className={styles.axis}>
        <span>{first.time}</span>
        <span>{middle.time}</span>
        <span>{last.time}</span>
      </div>
      <div className={styles.legend}>
        <span className={styles.legendLabel}>
          {t("cloud.heatmapLow", "低")}
        </span>
        {LEVEL_COLORS.map((color) => (
          <span
            key={color}
            className={styles.legendCell}
            style={{ background: color }}
          />
        ))}
        <span className={styles.legendLabel}>
          {t("cloud.heatmapHigh", "高")}
        </span>
      </div>
    </div>
  );
}
