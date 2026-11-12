import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Gauge, loadTone, Meta, percentTone, Readout } from "./NodeDashboard";
import styles from "./NodeDashboard.module.less";

export type ClusterNodeMetrics = {
  cpu?: number;
  mem?: number;
  disk?: number;
  load?: number;
  netIn?: number;
  netOut?: number;
  cores: number;
};

/** 点阵条最多画这么多根；节点更多时按 CPU 降序分桶。 */
const MAX_BARS = 72;

function finite(values: (number | undefined)[]): number[] {
  return values.filter(
    (value): value is number =>
      typeof value === "number" && Number.isFinite(value),
  );
}

function avg(values: number[]): number | null {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/**
 * 集群点阵条：每根柱子代表一个节点；节点数超过 MAX_BARS 时把节点按 CPU
 * 降序分桶，柱高取桶内均值，从而在有限宽度里保留整体负载分布形状。
 */
function ClusterBars({ values }: { values: number[] }) {
  const bars = useMemo(() => {
    if (!values.length) return [] as { avg: number; max: number }[];
    const sorted = [...values].sort((a, b) => b - a);
    if (sorted.length <= MAX_BARS) {
      return sorted.map((value) => ({ avg: value, max: value }));
    }
    const size = sorted.length / MAX_BARS;
    const out: { avg: number; max: number }[] = [];
    for (let index = 0; index < MAX_BARS; index += 1) {
      const from = Math.floor(index * size);
      const to = Math.max(Math.floor((index + 1) * size), from + 1);
      const slice = sorted.slice(from, to);
      if (!slice.length) continue;
      out.push({
        avg: slice.reduce((sum, value) => sum + value, 0) / slice.length,
        max: Math.max(...slice),
      });
    }
    return out;
  }, [values]);

  if (!bars.length) return <div className={styles.barsEmpty} />;

  return (
    <div className={styles.bars}>
      {bars.map((bar, index) => {
        const ratio = Math.max(0, Math.min(1, bar.avg / 100));
        return (
          <span
            key={`${index}-${bar.max.toFixed(1)}`}
            className={styles.bar}
            style={{
              height: `${Math.max(8, ratio * 100)}%`,
              background: percentTone(bar.avg),
              opacity: 0.4 + ratio * 0.6,
            }}
            title={`${bar.avg.toFixed(0)}%`}
          />
        );
      })}
    </div>
  );
}

export default function ClusterDashboard({
  nodes,
}: {
  nodes: ClusterNodeMetrics[];
}) {
  const { t } = useTranslation();

  const cpuValues = finite(nodes.map((node) => node.cpu));
  const memValues = finite(nodes.map((node) => node.mem));
  const diskValues = finite(nodes.map((node) => node.disk));
  const netInValues = finite(nodes.map((node) => node.netIn));
  const netOutValues = finite(nodes.map((node) => node.netOut));

  const cpuAvg = avg(cpuValues);
  const cpuPeak = cpuValues.length ? Math.max(...cpuValues) : null;
  const memAvg = avg(memValues);
  const memPeak = memValues.length ? Math.max(...memValues) : null;
  const diskAvg = avg(diskValues);
  const diskPeak = diskValues.length ? Math.max(...diskValues) : null;

  const totalCores = nodes.reduce((sum, node) => sum + (node.cores || 1), 0);
  const loadedNodes = nodes.filter(
    (node) => typeof node.load === "number" && Number.isFinite(node.load),
  );
  const totalLoad = loadedNodes.length
    ? loadedNodes.reduce((sum, node) => sum + (node.load ?? 0), 0)
    : null;
  const loadedCores = loadedNodes.reduce(
    (sum, node) => sum + (node.cores || 1),
    0,
  );
  const loadPerCore =
    totalLoad !== null && loadedCores > 0 ? totalLoad / loadedCores : null;

  const netInTotal = netInValues.length
    ? netInValues.reduce((sum, value) => sum + value, 0)
    : null;
  const netOutTotal = netOutValues.length
    ? netOutValues.reduce((sum, value) => sum + value, 0)
    : null;
  const netSum = (netInTotal ?? 0) + (netOutTotal ?? 0);
  const inRatio = netSum > 0 ? (netInTotal ?? 0) / netSum : 0;
  const outRatio = netSum > 0 ? (netOutTotal ?? 0) / netSum : 0;

  const busyCount = cpuValues.filter((value) => value >= 80).length;

  const formatNet = (value: number | null): string => {
    if (value === null) return "—";
    if (value >= 1000) return `${(value / 1000).toFixed(2)} G`;
    return `${value.toFixed(value >= 10 ? 0 : 1)} M`;
  };

  return (
    <div className={styles.dash}>
      <section className={styles.hero}>
        <div className={styles.heroTop}>
          <div className={styles.heroFigure}>
            <span className={styles.heroValue}>
              {cpuAvg === null ? "—" : cpuAvg.toFixed(0)}
            </span>
            <span className={styles.heroUnit}>%</span>
          </div>
          <span className={styles.heroTag}>
            {t("cloud.clusterCpu")} · {nodes.length}{" "}
            {t("cloud.clusterNodeUnit")}
          </span>
        </div>

        <ClusterBars values={cpuValues} />

        <div className={styles.heroMeta}>
          <Meta
            label={t("cloud.clusterNodeCount")}
            value={nodes.length}
            tone="var(--nd-green)"
          />
          <Meta
            label={t("cloud.kpiPeak")}
            value={cpuPeak === null ? "—" : `${cpuPeak.toFixed(0)}%`}
            tone="var(--nd-red)"
          />
          <Meta
            label={t("cloud.kpiAverage")}
            value={cpuAvg === null ? "—" : `${cpuAvg.toFixed(0)}%`}
            tone="var(--nd-orange)"
          />
          <Meta
            label={t("cloud.clusterOverloaded")}
            value={busyCount}
            tone="var(--nd-track)"
          />
        </div>
      </section>

      <div className={styles.grid}>
        <section className={styles.card}>
          <span className={styles.cardLabel}>{t("cloud.metricMem")}</span>
          <div className={styles.cardBody}>
            <Gauge
              ratio={memAvg == null ? 0 : memAvg / 100}
              color={percentTone(memAvg)}
            >
              {memAvg === null ? "—" : `${memAvg.toFixed(0)}%`}
            </Gauge>
            <div className={styles.readouts}>
              <Readout
                label={t("cloud.kpiAverage")}
                value={memAvg === null ? "—" : `${memAvg.toFixed(1)}%`}
              />
              <Readout
                label={t("cloud.kpiPeak")}
                value={memPeak === null ? "—" : `${memPeak.toFixed(1)}%`}
              />
            </div>
          </div>
        </section>

        <section className={styles.card}>
          <span className={styles.cardLabel}>{t("cloud.metricLoad")}</span>
          <div className={styles.cardBody}>
            <Gauge
              ratio={loadPerCore == null ? 0 : Math.min(1, loadPerCore)}
              color={loadTone(loadPerCore)}
            >
              {totalLoad === null
                ? "—"
                : (totalLoad / Math.max(loadedNodes.length, 1)).toFixed(2)}
            </Gauge>
            <div className={styles.readouts}>
              <Readout
                label={t("cloud.clusterTotalCores")}
                value={`${totalCores}`}
              />
              <Readout
                label={t("cloud.nodePerCore")}
                value={loadPerCore == null ? "—" : loadPerCore.toFixed(2)}
              />
            </div>
          </div>
        </section>

        <section className={styles.card}>
          <span className={styles.cardLabel}>{t("cloud.metricDisk")}</span>
          <div className={styles.cardBody}>
            <Gauge
              ratio={diskAvg == null ? 0 : diskAvg / 100}
              color={percentTone(diskAvg)}
            >
              {diskAvg === null ? "—" : `${diskAvg.toFixed(0)}%`}
            </Gauge>
            <div className={styles.readouts}>
              <Readout
                label={t("cloud.kpiAverage")}
                value={diskAvg === null ? "—" : `${diskAvg.toFixed(1)}%`}
              />
              <Readout
                label={t("cloud.kpiPeak")}
                value={diskPeak === null ? "—" : `${diskPeak.toFixed(1)}%`}
              />
            </div>
          </div>
        </section>

        <section className={styles.card}>
          <span className={styles.cardLabel}>{t("cloud.nodeNetwork")}</span>
          <div className={styles.cardBody}>
            <Gauge
              ratio={inRatio}
              color="var(--nd-orange)"
              size={52}
              stroke={6}
            >
              <span className={styles.netArrow}>↓</span>
            </Gauge>
            <Gauge
              ratio={outRatio}
              color="var(--nd-green)"
              size={52}
              stroke={6}
            >
              <span className={styles.netArrow}>↑</span>
            </Gauge>
            <div className={styles.readouts}>
              <Readout
                label={t("cloud.metricNetIn")}
                value={formatNet(netInTotal)}
              />
              <Readout
                label={t("cloud.metricNetOut")}
                value={formatNet(netOutTotal)}
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
