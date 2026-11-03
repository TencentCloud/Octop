import type { ReactNode } from "react";

import { levelTone } from "../theme";
import styles from "./NodeOverview.module.less";

export type NodeHealth = "online" | "warn" | "alert" | "offline" | "unknown";

export type NodeLoad = {
  /** `${region}:${instance_id}` */
  id: string;
  name: string;
  ip: string;
  health: NodeHealth;
  rawState: string;
  /** 真实采样值；没采到就保持 null，界面用"—"呈现 */
  cpu: number | null;
  mem: number | null;
  disk: number | null;
  netIn: number | null;
  netOut: number | null;
  cores: number;
  load: number | null;
};

const HEALTH_ORDER: NodeHealth[] = [
  "online",
  "warn",
  "alert",
  "offline",
  "unknown",
];

const HEALTH_LABEL: Record<NodeHealth, string> = {
  online: "在线",
  warn: "偏高",
  alert: "告警",
  offline: "离线",
  unknown: "未知",
};

/** 资源条颜色见 theme.levelTone：<40 绿、40–59 蓝、60–79 橙、≥80 红。 */
function toneOf(value: number): string {
  return levelTone(value).stroke;
}

function formatNet(value: number | null): string {
  if (value === null) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}G`;
  return `${value.toFixed(value >= 10 ? 0 : 1)}M`;
}

export function countHealth(rows: NodeLoad[]): Record<NodeHealth, number> {
  const counts: Record<NodeHealth, number> = {
    online: 0,
    warn: 0,
    alert: 0,
    offline: 0,
    unknown: 0,
  };
  for (const row of rows) counts[row.health] += 1;
  return counts;
}

/** 状态汇总 + 全局占比条，右侧可插槽（视图切换等）。 */
export function NodeStatusSummary({
  rows,
  right,
}: {
  rows: NodeLoad[];
  right?: ReactNode;
}) {
  const counts = countHealth(rows);
  const total = rows.length || 1;

  return (
    <section className={styles.summary}>
      <div className={styles.summaryHead}>
        <div className={styles.summaryCards}>
          {HEALTH_ORDER.map((key) => (
            <div key={key} className={styles.summaryCard} data-health={key}>
              <span className={styles.summaryLabel}>
                <i className={styles.summaryDot} />
                {HEALTH_LABEL[key]}
              </span>
              <span className={styles.summaryValue}>{counts[key]}</span>
              <span className={styles.summaryHint}>
                {Math.round((counts[key] / total) * 100)}%
              </span>
            </div>
          ))}
        </div>
        {right ? <div className={styles.summaryActions}>{right}</div> : null}
      </div>

      <div className={styles.ratioBar} role="img" aria-label="节点健康占比">
        {HEALTH_ORDER.map((key) =>
          counts[key] ? (
            <span
              key={key}
              className={styles.ratioSeg}
              data-health={key}
              style={{ flexGrow: counts[key] }}
              title={`${HEALTH_LABEL[key]} ${counts[key]} 台`}
            />
          ) : null,
        )}
      </div>
    </section>
  );
}

/** 节点卡片网格：一屏对比所有节点的 CPU / 内存 / 磁盘 / 网络。 */
export default function NodeGrid({
  rows,
  onSelect,
}: {
  rows: NodeLoad[];
  onSelect: (row: NodeLoad) => void;
}) {
  if (!rows.length) {
    return <div className={styles.empty}>当前范围内没有节点</div>;
  }

  return (
    <div className={styles.grid}>
      {rows.map((row) => (
        <button
          key={row.id}
          type="button"
          className={styles.card}
          data-health={row.health}
          onClick={() => onSelect(row)}
          title={`${row.name} · ${row.ip}`}
        >
          <div className={styles.cardHead}>
            <i className={styles.dot} data-health={row.health} />
            <span className={styles.name}>{row.name}</span>
            <span className={styles.badge} data-health={row.health}>
              {HEALTH_LABEL[row.health]}
            </span>
          </div>

          <div className={styles.metrics}>
            <Metric label="CPU" value={row.cpu} />
            <Metric label="内存" value={row.mem} />
            <Metric label="磁盘" value={row.disk} />
          </div>

          <div className={styles.cardFoot}>
            <span className={styles.net}>
              <b className={styles.netIn}>↓</b>
              {formatNet(row.netIn)}
              <b className={styles.netOut}>↑</b>
              {formatNet(row.netOut)}
            </span>
            <span className={styles.load}>
              {row.load === null ? "—" : row.load.toFixed(2)} / {row.cores} 核
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  const width = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className={styles.metric}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.track}>
        <span
          className={styles.fill}
          style={{
            width: `${width}%`,
            background: value === null ? "transparent" : toneOf(value),
          }}
        />
      </span>
      <span className={styles.metricValue}>
        {value === null ? "—" : `${value.toFixed(0)}%`}
      </span>
    </div>
  );
}
