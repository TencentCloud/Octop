import { useEffect } from "react";
import { X } from "lucide-react";

import { ALERT_MIN, WARN_MIN, levelTone } from "../theme";
import styles from "./NodeDetailDrawer.module.less";

export type DrawerNode = {
  name: string;
  ip: string;
  regionName: string;
  regionId: string;
  index: number;
  total: number;
  status: "healthy" | "warning" | "critical" | "offline";
  cpu: number | null;
  mem: number | null;
  disk: number | null;
  netIn: number | null;
  netOut: number | null;
  cores: number;
  memoryGib: number;
  osName: string;
  reason: string;
};

const STATUS_LABEL: Record<DrawerNode["status"], string> = {
  healthy: "健康",
  warning: "关注",
  critical: "异常",
  offline: "离线",
};

const METRIC_ROWS: Array<{ key: "cpu" | "mem" | "disk"; label: string }> = [
  { key: "cpu", label: "CPU" },
  { key: "mem", label: "内存" },
  { key: "disk", label: "磁盘" },
];

function noteBody(node: DrawerNode): string {
  if (node.status === "offline") {
    return "该节点已停止，不把缺失采样当作 0 计入平均值。";
  }
  if ((node.disk ?? 0) >= ALERT_MIN) {
    return "磁盘占用已达到 80%，建议尽快清理空间或扩容。";
  }
  if ((node.disk ?? 0) >= WARN_MIN) {
    return "磁盘占用处于 60%–80%，建议关注剩余空间。";
  }
  if (node.status === "critical") {
    return "该节点 CPU 或内存处于高负载区间，建议立即排查占用进程。";
  }
  if (node.status === "warning") {
    return "该节点有指标接近阈值，可切换矩阵视图观察资源趋势。";
  }
  return "该节点各项资源处于正常区间。";
}

export default function NodeDetailDrawer({
  node,
  onClose,
  onOpenFull,
}: {
  node: DrawerNode | null;
  onClose: () => void;
  onOpenFull?: () => void;
}) {
  useEffect(() => {
    if (!node) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [node, onClose]);

  if (!node) return null;

  const meta: Array<[string, string]> = [
    ["私网地址", node.ip],
    ["地域标识", node.regionId],
    ["规格", `${node.cores} vCPU / ${node.memoryGib} GiB`],
    ["节点编号", `${String(node.index).padStart(2, "0")} / ${node.total}`],
    ["系统", node.osName || "—"],
    [
      "采样状态",
      node.status === "offline" ? "离线 · 无采样" : "1 分钟粒度 · 实时",
    ],
  ];

  return (
    <div className={styles.backdrop} role="presentation" onClick={onClose}>
      <section
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-label={`${node.name} 节点详情`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={styles.titlebar}>
          <div>
            <div className={styles.eyebrow}>NODE INSPECTOR / 节点详情</div>
            <h2 className={styles.title}>{node.name}</h2>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="关闭节点详情"
          >
            <X size={16} />
          </button>
        </div>

        <span className={styles.badge}>
          <i className={styles.badgeDot} />
          实时采样 · 只读
        </span>

        <div className={styles.statusRow}>
          <span className={styles.statusBadge} data-status={node.status}>
            <i className={styles.statusDot} />
            {STATUS_LABEL[node.status]}
          </span>
          <span className={styles.statusRegion}>{node.regionName}</span>
        </div>

        <dl className={styles.metaGrid}>
          {meta.map(([label, value]) => (
            <div key={label}>
              <dt className={styles.metaLabel}>{label}</dt>
              <dd className={styles.metaValue}>{value}</dd>
            </div>
          ))}
        </dl>

        <div className={styles.resource}>
          <h3 className={styles.resourceTitle}>当前资源使用</h3>
          {METRIC_ROWS.map((row) => {
            const value = node[row.key];
            const tone = levelTone(value);
            return (
              <div key={row.key} className={styles.metric}>
                <div className={styles.metricLabel}>
                  <span>{row.label}</span>
                  <strong style={{ color: tone.ink }}>
                    {value === null ? "—" : `${value.toFixed(1)}%`}
                  </strong>
                </div>
                <div
                  className={styles.track}
                  style={{ background: tone.track }}
                >
                  <span
                    style={{
                      width: `${value === null ? 0 : Math.min(100, value)}%`,
                      background: tone.stroke,
                    }}
                  />
                </div>
              </div>
            );
          })}

          <div className={styles.networkRow}>
            <span>网络 · 入站 / 出站</span>
            <strong>
              {node.netIn === null || node.netOut === null
                ? "—"
                : `${node.netIn.toFixed(1)} / ${node.netOut.toFixed(1)} Mbps`}
            </strong>
          </div>
        </div>

        <div className={styles.note} data-status={node.status}>
          <strong>{node.reason}</strong>
          {noteBody(node)}
        </div>

        <p className={styles.help}>
          此视图展示该实例的实时采样指标。不会对服务器执行任何命令，也不发起重启、
          扩缩容或授权请求。
        </p>

        <div className={styles.footer}>
          <span>ESC 关闭 · 点击遮罩关闭</span>
          {onOpenFull ? (
            <button
              type="button"
              className={styles.fullBtn}
              onClick={onOpenFull}
            >
              查看完整监控
            </button>
          ) : (
            <span>
              {new Date().toLocaleTimeString("zh-CN", { hour12: false })}
            </span>
          )}
        </div>
      </section>
    </div>
  );
}
