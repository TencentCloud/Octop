import { useMemo, useState } from "react";
import {
  Activity,
  Cloud,
  Cpu,
  Network,
  Server,
  Shield,
  ShieldAlert,
} from "lucide-react";

import { ALERT_MIN, WARN_MIN, levelTone, TONE } from "../theme";
import NodeDetailDrawer, { type DrawerNode } from "./NodeDetailDrawer";
import styles from "./CloudOverviewBoard.module.less";

type Health = "healthy" | "warning" | "critical" | "offline";

export type BoardInstance = {
  instance_id: string;
  name: string;
  region: string;
  zone: string;
  state: string;
  os_name: string;
  cpu: number;
  memory_gb: number;
  private_ips: string[];
  public_ips: string[];
};

export type BoardRegion = { id: string; name: string };

export type BoardNode = {
  id: string;
  name: string;
  ip: string;
  region: string;
  regionName: string;
  index: number;
  health: Health;
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

const HEALTH_LABEL: Record<Health, string> = {
  healthy: "健康",
  warning: "关注",
  critical: "异常",
  offline: "离线",
};

// 健康绿、关注（60%–80%）橙、异常（≥80%）红、离线灰
const HEALTH_COLOR: Record<Health, [string, string, string]> = {
  healthy: ["#dff3e9", "#398b6e", "#c4e8d7"],
  warning: ["#fdf3e8", "#c56a12", "#f3d7b4"],
  critical: ["#fdefef", "#c64756", "#f4d0d4"],
  offline: ["#f1f3f6", "#a3abb8", "#dce0e6"],
};

function toHealth(
  state: string,
  cpu: number | null,
  mem: number | null,
  disk: number | null,
): Health {
  if (state === "STOPPED") return "offline";
  // 没采到数据时不能当成健康的 0 值，统一走"离线 / 无采样"这一档
  if (cpu === null && mem === null) return "offline";
  const peak = Math.max(cpu ?? 0, mem ?? 0, disk ?? 0);
  if (peak >= ALERT_MIN) return "critical";
  if (peak >= WARN_MIN) return "warning";
  return "healthy";
}

function reasonOf(
  health: Health,
  state: string,
  cpu: number | null,
  mem: number | null,
  disk: number | null,
): string {
  if (health === "offline") {
    return state === "STOPPED" ? "已停止 · 无采样" : "暂无监控数据";
  }
  if ((disk ?? 0) >= ALERT_MIN) return "磁盘占用过高";
  if ((disk ?? 0) >= WARN_MIN) return "磁盘空间偏高";
  if ((cpu ?? 0) >= ALERT_MIN) return "CPU 高负载";
  if ((mem ?? 0) >= ALERT_MIN) return "内存使用偏高";
  if ((cpu ?? 0) >= WARN_MIN || (mem ?? 0) >= WARN_MIN) return "资源持续偏高";
  return "指标在正常范围";
}

/** 迷你折线：不依赖图表库，直接画路径。 */
function Spark({ values, color }: { values: number[]; color: string }) {
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 4);
  const points = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * 88 + 1;
    const y = 30 - ((value - min) / span) * 22;
    return [x, y] as const;
  });
  const d = points
    .map(
      ([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`,
    )
    .join(" ");

  return (
    <svg className={styles.spark} viewBox="0 0 90 34" aria-hidden="true">
      <path d={`${d} L89 34 L1 34 Z`} fill={color} opacity="0.08" />
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Ring({ percent, color }: { percent: number; color: string }) {
  const radius = 16;
  const circumference = 2 * Math.PI * radius;
  const value = Math.max(0, Math.min(100, percent)) / 100;
  return (
    <svg className={styles.kpiRing} viewBox="0 0 40 40" aria-hidden="true">
      <circle
        cx="20"
        cy="20"
        r={radius}
        fill="none"
        stroke="#edf3f0"
        strokeWidth="3.4"
      />
      <circle
        cx="20"
        cy="20"
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeDasharray={`${(circumference * value).toFixed(
          1,
        )} ${circumference.toFixed(1)}`}
        transform="rotate(-90 20 20)"
      />
    </svg>
  );
}

export type TrendPoint = {
  t: number;
  cpu?: number;
  mem?: number;
  net_in?: number;
  net_out?: number;
};

export default function CloudOverviewBoard({
  instances,
  clusterMetrics,
  regions,
  metric,
  onMetricChange,
  onSelectNode,
  trend,
  trendSampled,
  trendTotal,
  trendLoading,
  sampledAt,
}: {
  instances: BoardInstance[];
  clusterMetrics: Record<string, Record<string, number>>;
  regions: BoardRegion[];
  metric: "health" | "cpu" | "mem";
  onMetricChange: (value: "health" | "cpu" | "mem") => void;
  onSelectNode: (row: BoardInstance) => void;
  trend: TrendPoint[];
  trendSampled: number;
  trendTotal: number;
  trendLoading: boolean;
  sampledAt: number;
}) {
  const nodes = useMemo<BoardNode[]>(() => {
    const regionNameOf = new Map(regions.map((item) => [item.id, item.name]));
    const counters = new Map<string, number>();

    return instances.map((row) => {
      const index = (counters.get(row.region) ?? 0) + 1;
      counters.set(row.region, index);

      const metricRow = clusterMetrics[row.instance_id] ?? {};
      const stopped = row.state === "STOPPED";
      // 只认真实采样值：缺失就保持 null，用"—"呈现，不再生成演示数据
      const read = (key: string): number | null => {
        if (stopped) return null;
        const raw = metricRow[key];
        return typeof raw === "number" && Number.isFinite(raw) ? raw : null;
      };

      const cpu = read("cpu");
      const mem = read("mem");
      const disk = read("disk_usage");
      const netIn = read("net_in");
      const netOut = read("net_out");

      const health = toHealth(row.state, cpu, mem, disk);

      return {
        id: `${row.region}:${row.instance_id}`,
        name: row.name,
        ip: row.private_ips[0] || row.public_ips[0] || row.instance_id,
        region: row.region,
        regionName: regionNameOf.get(row.region) ?? row.region,
        index,
        health,
        cpu,
        mem,
        disk,
        netIn,
        netOut,
        cores: row.cpu || 1,
        memoryGib: Math.round((row.memory_gb || 0) * 1.073741824),
        osName: row.os_name || "",
        reason: reasonOf(health, row.state, cpu, mem, disk),
      };
    });
  }, [instances, clusterMetrics, regions]);

  const [activeNode, setActiveNode] = useState<BoardNode | null>(null);

  const drawerNode: DrawerNode | null = activeNode
    ? {
        name: activeNode.name,
        ip: activeNode.ip,
        regionName: activeNode.regionName,
        regionId: activeNode.region,
        index: activeNode.index,
        total: nodes.filter((item) => item.region === activeNode.region).length,
        status: activeNode.health,
        cpu: activeNode.cpu,
        mem: activeNode.mem,
        disk: activeNode.disk,
        netIn: activeNode.netIn,
        netOut: activeNode.netOut,
        cores: activeNode.cores,
        memoryGib: activeNode.memoryGib,
        osName: activeNode.osName,
        reason: activeNode.reason,
      }
    : null;

  // 地域筛选由页面顶部的地区选择器完成，这里直接用已过滤的实例集合
  const visible = nodes;

  const summary = useMemo(() => {
    const online = visible.filter((node) => node.health !== "offline");
    const healthy = visible.filter((node) => node.health === "healthy").length;
    const warning = visible.filter((node) => node.health === "warning").length;
    const critical = visible.filter(
      (node) => node.health === "critical",
    ).length;
    const cpuValues = online.map((node) => node.cpu ?? 0);
    const memValues = online.map((node) => node.mem ?? 0);
    const netIn = online.reduce((sum, node) => sum + (node.netIn ?? 0), 0);
    const netOut = online.reduce((sum, node) => sum + (node.netOut ?? 0), 0);

    return {
      total: visible.length,
      online: online.length,
      offline: visible.length - online.length,
      healthy,
      warning,
      critical,
      attention: warning + critical,
      healthyRatio: online.length ? (healthy / online.length) * 100 : 0,
      onlineRatio: visible.length ? (online.length / visible.length) * 100 : 0,
      cpuAvg: cpuValues.length
        ? cpuValues.reduce((a, b) => a + b, 0) / cpuValues.length
        : null,
      cpuPeak: cpuValues.length ? Math.max(...cpuValues) : null,
      memAvg: memValues.length
        ? memValues.reduce((a, b) => a + b, 0) / memValues.length
        : null,
      netIn,
      netOut,
      netTotal: netIn + netOut,
      totalCores: visible.reduce((sum, node) => sum + node.cores, 0),
    };
  }, [visible]);

  const grouped = useMemo(() => {
    return regions
      .map((region) => {
        const items = visible.filter((node) => node.region === region.id);
        return { region, items };
      })
      .filter((group) => group.items.length > 0);
  }, [regions, visible]);

  const attention = useMemo(
    () =>
      visible
        .filter(
          (node) => node.health === "warning" || node.health === "critical",
        )
        .sort(
          (a, b) =>
            (b.health === "critical" ? 1 : 0) -
              (a.health === "critical" ? 1 : 0) || (b.cpu ?? 0) - (a.cpu ?? 0),
        )
        .slice(0, 5),
    [visible],
  );

  // 趋势曲线直接用后端返回的真实序列，不做任何插值或模拟
  const cpuSeries = useMemo(
    () =>
      trend
        .map((point) => point.cpu)
        .filter((value): value is number => typeof value === "number"),
    [trend],
  );

  const netSeries = useMemo(
    () =>
      trend
        .map((point) => (point.net_in ?? 0) + (point.net_out ?? 0))
        .filter((value) => value > 0),
    [trend],
  );

  const tone = (node: BoardNode): [string, string, string] => {
    if (node.health === "offline") return HEALTH_COLOR.offline;
    if (metric === "health") return HEALTH_COLOR[node.health];
    const tone = levelTone(node[metric]);
    return [tone.bg, tone.ink, tone.stroke];
  };

  const valueOf = (node: BoardNode): string => {
    if (node.health === "offline") return "—";
    if (metric === "health") return String(node.index).padStart(2, "0");
    return (node[metric] ?? 0).toFixed(0);
  };

  const unitOf = (value: number): { value: string; unit: string } => {
    if (value >= 1000)
      return { value: (value / 1000).toFixed(2), unit: "Gbps" };
    return { value: value.toFixed(0), unit: "Mbps" };
  };

  const net = unitOf(summary.netTotal);

  return (
    <div className={styles.board}>
      <div className={styles.summaryBand}>
        <Shield size={14} className={styles.bandIcon} />
        <span className={styles.bandMain}>
          {!summary.total
            ? "暂无匹配节点"
            : summary.critical
            ? "集群整体稳态 · 局部负载异常"
            : "集群整体稳态"}
        </span>
        <span className={styles.bandSep}>/</span>
        <span>{summary.attention} 个节点需要关注</span>
        <span className={styles.bandTime}>
          {sampledAt
            ? `采样 ${new Date(sampledAt * 1000).toLocaleTimeString("zh-CN", {
                hour12: false,
              })}`
            : "等待采样"}
        </span>
      </div>

      <section className={styles.kpiGrid}>
        <article className={styles.kpi}>
          <div className={styles.kpiHead}>
            <span>在线节点</span>
            <span className={styles.kpiIcon}>
              <Server size={13} />
            </span>
          </div>
          <div className={styles.kpiValue}>
            {summary.online}
            <span className={styles.kpiUnit}>/ {summary.total}</span>
          </div>
          <div className={styles.kpiFoot}>
            <span className={styles.miniTag}>
              {summary.onlineRatio.toFixed(1)}% 在线
            </span>
            <span>{summary.offline} 离线 / 无采样</span>
          </div>
        </article>

        <article className={styles.kpi}>
          <div className={styles.kpiHead}>
            <span>在线节点健康比例</span>
            <span className={styles.kpiIcon}>
              <Shield size={13} />
            </span>
          </div>
          <div className={styles.kpiValue}>
            {summary.healthyRatio.toFixed(1)}
            <span className={styles.kpiUnit}>%</span>
          </div>
          <Ring percent={summary.healthyRatio} color="#43b68e" />
          <div className={styles.kpiFoot}>
            <span className={styles.miniTag}>{summary.healthy} 健康</span>
            <span>{summary.attention} 需关注</span>
          </div>
        </article>

        <article className={styles.kpi}>
          <div className={styles.kpiHead}>
            <span>CPU 平均使用率</span>
            <span className={styles.kpiIcon}>
              <Cpu size={13} />
            </span>
          </div>
          <div className={styles.kpiValue}>
            {summary.cpuAvg === null ? "—" : summary.cpuAvg.toFixed(1)}
            <span className={styles.kpiUnit}>%</span>
          </div>
          <Spark values={cpuSeries} color="#4a86d8" />
          <div className={styles.kpiFoot}>
            <span className={styles.okText}>
              {summary.cpuAvg === null
                ? "暂无采样"
                : summary.cpuAvg >= WARN_MIN
                ? "负载偏高"
                : "负载适中"}
            </span>
            <span>
              峰值{" "}
              {summary.cpuPeak === null
                ? "—"
                : `${summary.cpuPeak.toFixed(0)}%`}
            </span>
          </div>
        </article>

        <article className={styles.kpi}>
          <div className={styles.kpiHead}>
            <span>集群网络吞吐</span>
            <span className={styles.kpiIcon}>
              <Network size={13} />
            </span>
          </div>
          <div className={styles.kpiValue}>
            {net.value}
            <span className={styles.kpiUnit}>{net.unit}</span>
          </div>
          <Spark values={netSeries} color="#87a4ce" />
          <div className={styles.kpiFoot}>
            <span>↓ {summary.netIn.toFixed(0)} M</span>
            <span className={styles.faint}>/</span>
            <span>↑ {summary.netOut.toFixed(0)} M</span>
          </div>
        </article>
      </section>

      <div className={styles.contentGrid}>
        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <div>
              <div className={styles.panelTitleRow}>
                <h2 className={styles.panelTitle}>节点运行矩阵</h2>
                <span className={styles.count}>{visible.length}</span>
              </div>
              <p className={styles.panelSub}>
                按地域分组 · 点击节点查看指标详情
              </p>
            </div>
            <div className={styles.segmented}>
              {(
                [
                  ["health", "健康"],
                  ["cpu", "CPU"],
                  ["mem", "内存"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={metric === key ? styles.segActive : ""}
                  onClick={() => onMetricChange(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.matrixGroups}>
            {grouped.map((group) => {
              const onlineCount = group.items.filter(
                (item) => item.health !== "offline",
              ).length;
              const attentionCount = group.items.filter(
                (item) =>
                  item.health === "warning" || item.health === "critical",
              ).length;
              return (
                <div key={group.region.id} className={styles.regionGroup}>
                  <div className={styles.regionTitle}>
                    <span className={styles.regionName}>
                      <i className={styles.regionMark} />
                      {group.region.name}
                    </span>
                    <span className={styles.regionTotal}>
                      {onlineCount}/{group.items.length} 在线
                      {attentionCount ? ` · ${attentionCount} 关注` : ""}
                    </span>
                  </div>
                  <div className={styles.nodeGrid}>
                    {group.items.map((node) => {
                      const [bg, ink, line] = tone(node);
                      return (
                        <button
                          key={node.id}
                          type="button"
                          className={styles.tile}
                          data-health={node.health}
                          style={{
                            background: bg,
                            color: ink,
                            borderColor: line,
                          }}
                          title={`${node.name} · ${
                            HEALTH_LABEL[node.health]
                          } · CPU ${node.cpu?.toFixed(0) ?? "—"}% · 内存 ${
                            node.mem?.toFixed(0) ?? "—"
                          }%`}
                          onClick={() => setActiveNode(node)}
                        >
                          <i className={styles.tileDot} />
                          <span>{valueOf(node)}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
            {!grouped.length ? (
              <div className={styles.empty}>当前筛选无匹配节点</div>
            ) : null}
          </div>

          <div className={styles.matrixLegend}>
            {(metric === "health"
              ? [
                  ["健康", TONE.good.stroke],
                  ["关注", TONE.warn.stroke],
                  ["异常", TONE.alert.stroke],
                  ["离线", TONE.offline.stroke],
                ]
              : [
                  ["<40%", TONE.good.stroke],
                  ["40–59%", TONE.normal.stroke],
                  ["60–79%", TONE.warn.stroke],
                  ["≥80%", TONE.alert.stroke],
                  ["离线 / 无采样", TONE.offline.stroke],
                ]
            ).map(([label, color]) => (
              <span key={label} className={styles.legendItem}>
                <i
                  className={styles.legendSquare}
                  style={{ background: color, borderColor: color }}
                />
                {label}
              </span>
            ))}
            <span className={styles.legendNote}>
              {metric === "health"
                ? "编号 = 地域内节点序号"
                : "颜色仅表示当前资源负载"}
            </span>
          </div>
        </section>

        <div className={styles.rightStack}>
          <section className={styles.panel}>
            <div className={styles.panelHead}>
              <div>
                <h2 className={styles.panelTitle}>集群资源趋势</h2>
                <p className={styles.panelSub}>
                  {trendLoading
                    ? "加载中…"
                    : trend.length
                    ? `抽样 ${trendSampled}/${trendTotal} 台均值 · 1 分钟粒度`
                    : "暂无采样数据"}
                </p>
              </div>
              <Activity size={14} className={styles.headIcon} />
            </div>
            <div className={styles.trendLegend}>
              <span>
                <i className={styles.lineMark} />
                CPU <b>{summary.cpuAvg?.toFixed(1) ?? "—"}%</b>
              </span>
              <span>
                <i className={`${styles.lineMark} ${styles.lineMarkBlue}`} />
                内存 <b>{summary.memAvg?.toFixed(1) ?? "—"}%</b>
              </span>
            </div>
            <svg
              className={styles.trendSvg}
              viewBox="0 0 390 150"
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient id="boardCpuFill" x1="0" y1="0" x2="0" y2="1">
                  <stop stopColor="#4a86d8" stopOpacity="0.12" />
                  <stop offset="1" stopColor="#4a86d8" stopOpacity="0" />
                </linearGradient>
              </defs>
              {[0, 25, 50, 75, 100].map((value) => {
                const y = 130 - (value / 100) * 118;
                return (
                  <g key={value}>
                    <line
                      x1="30"
                      y1={y}
                      x2="384"
                      y2={y}
                      stroke="#edf0f4"
                      strokeDasharray="3 4"
                    />
                    <text
                      x="24"
                      y={y + 3}
                      textAnchor="end"
                      fill="#aab2bf"
                      fontSize="10"
                    >
                      {value}
                    </text>
                  </g>
                );
              })}
              {(["mem", "cpu"] as const).map((key) => {
                const valid = trend.filter(
                  (point) => typeof point[key] === "number",
                );
                if (valid.length < 2) return null;
                const path = valid
                  .map((point, index) => {
                    const x = 30 + (index / (valid.length - 1)) * 354;
                    const y = 130 - ((point[key] as number) / 100) * 118;
                    return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(
                      1,
                    )}`;
                  })
                  .join(" ");
                return (
                  <path
                    key={key}
                    d={path}
                    fill="none"
                    stroke={key === "cpu" ? "#4a86d8" : "#8b7fd4"}
                    strokeWidth="1.65"
                    strokeLinejoin="round"
                  />
                );
              })}
            </svg>
            {!trend.length && !trendLoading ? (
              <div className={styles.trendEmpty}>暂无采样数据</div>
            ) : null}
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHead}>
              <h2 className={styles.panelTitle}>地域资源分布</h2>
              <span className={styles.panelSub}>vCPU / 在线</span>
            </div>
            <div className={styles.resourceRows}>
              {grouped.map((group) => {
                const cores = group.items.reduce(
                  (sum, item) => sum + item.cores,
                  0,
                );
                const share = summary.totalCores
                  ? (cores / summary.totalCores) * 100
                  : 0;
                const onlineCount = group.items.filter(
                  (item) => item.health !== "offline",
                ).length;
                return (
                  <div key={group.region.id} className={styles.resourceRow}>
                    <span className={styles.resourceName}>
                      {group.region.name}
                      <i>{cores}c</i>
                    </span>
                    <div className={styles.resourceBar}>
                      <span style={{ width: `${share}%` }} />
                    </div>
                    <span className={styles.resourceNumber}>
                      {onlineCount}/{group.items.length}
                    </span>
                  </div>
                );
              })}
              {!grouped.length ? (
                <div className={styles.empty}>暂无地域资源</div>
              ) : null}
            </div>
          </section>
        </div>
      </div>

      <div className={styles.bottomGrid}>
        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <div className={styles.panelTitleRow}>
              <h2 className={styles.panelTitle}>需要关注的节点</h2>
              <span className={styles.alertCount}>{attention.length}</span>
            </div>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>节点</th>
                  <th>地址 / 地域</th>
                  <th>CPU</th>
                  <th>内存</th>
                  <th>关注原因</th>
                </tr>
              </thead>
              <tbody>
                {attention.map((node) => (
                  <tr key={node.id}>
                    <td>
                      <button
                        type="button"
                        className={styles.nodeNameBtn}
                        onClick={() => setActiveNode(node)}
                      >
                        <i
                          className={styles.rowDot}
                          data-health={node.health}
                        />
                        {node.name}
                      </button>
                    </td>
                    <td>
                      <strong className={styles.cellMain}>
                        {node.regionName}
                      </strong>
                      <div className={styles.cellSub}>{node.ip}</div>
                    </td>
                    <td>
                      <span className={styles.metricNumber}>
                        {node.cpu === null ? "—" : `${node.cpu.toFixed(1)}%`}
                      </span>
                    </td>
                    <td>
                      <span className={styles.metricNumber}>
                        {node.mem === null ? "—" : `${node.mem.toFixed(1)}%`}
                      </span>
                    </td>
                    <td>
                      <span
                        className={styles.reasonTag}
                        data-health={node.health}
                      >
                        {node.reason}
                      </span>
                    </td>
                  </tr>
                ))}
                {!attention.length ? (
                  <tr>
                    <td colSpan={5} className={styles.tableEmpty}>
                      当前地域无关注 / 异常节点
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>监控事件</h2>
            <span className={styles.softBadge}>最近采样</span>
          </div>
          <div className={styles.events}>
            {attention.slice(0, 4).map((node) => (
              <div key={node.id} className={styles.event}>
                <i className={styles.eventDot} data-health={node.health} />
                <div className={styles.eventBody}>
                  <div className={styles.eventTitle}>
                    <span>{node.reason}</span>
                    <span className={styles.eventTime}>
                      {sampledAt
                        ? new Date(sampledAt * 1000).toLocaleTimeString(
                            "zh-CN",
                            {
                              hour12: false,
                            },
                          )
                        : "—"}
                    </span>
                  </div>
                  <div className={styles.eventDesc}>
                    {node.name} · CPU {node.cpu?.toFixed(0) ?? "—"}% / 内存{" "}
                    {node.mem?.toFixed(0) ?? "—"}%
                  </div>
                </div>
              </div>
            ))}
            {!attention.length ? (
              <div className={styles.empty}>
                <ShieldAlert size={22} />
                <span>当前没有需要关注的事件</span>
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <div className={styles.footer}>
        <i className={styles.footerDot} />
        <span>
          {summary.totalCores} vCPU · {summary.total} 节点
        </span>
        <span className={styles.faint}>|</span>
        <span>
          采样覆盖 {summary.online}/{summary.total}
        </span>
        <span className={styles.footerRight}>
          <Cloud size={12} /> 数据来自腾讯云监控
        </span>
      </div>

      <NodeDetailDrawer
        node={drawerNode}
        onClose={() => setActiveNode(null)}
        onOpenFull={() => {
          if (!activeNode) return;
          const target = instances.find(
            (row) => `${row.region}:${row.instance_id}` === activeNode.id,
          );
          if (target) onSelectNode(target);
          setActiveNode(null);
        }}
      />
    </div>
  );
}
