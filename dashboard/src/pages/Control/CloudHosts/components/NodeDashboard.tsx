import { useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { levelTone, TONE } from "../theme";

import styles from "./NodeDashboard.module.less";

export type Point = { t: number; v: number };
export type Series = Record<string, Point[]>;

function finite(points: Point[]): number[] {
  return points
    .map((point) => point.v)
    .filter((value) => Number.isFinite(value));
}

function latestOf(points: Point[]): number | null {
  for (let index = points.length - 1; index >= 0; index -= 1) {
    if (Number.isFinite(points[index].v)) return points[index].v;
  }
  return null;
}

function averageOf(values: number[]): number | null {
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

/** 资源占用 0–100：<40 绿、40–59 蓝、60–79 橙、≥80 红。缺测为灰。 */
export function percentTone(value: number | null | undefined): string {
  return levelTone(value).stroke;
}

/** 每核负载：满 1 为红，0.7 起为蓝，缺测为灰。与节点详情一致。 */
export function loadTone(perCore: number | null | undefined): string {
  if (perCore == null || !Number.isFinite(perCore)) return TONE.offline.stroke;
  if (perCore >= 1) return TONE.alert.stroke;
  if (perCore >= 0.7) return TONE.normal.stroke;
  return TONE.good.stroke;
}

export function Gauge({
  ratio,
  color,
  size = 66,
  stroke = 7,
  children,
}: {
  ratio: number;
  color: string;
  size?: number;
  stroke?: number;
  children?: ReactNode;
}) {
  const clamped = Math.max(0, Math.min(1, ratio));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className={styles.gauge} style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--nd-track)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference * clamped} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dasharray 0.4s ease" }}
        />
      </svg>
      <div className={styles.gaugeText}>{children}</div>
    </div>
  );
}

/** Signature ServerCat detail: dense bars, one per sample, height + tone = load. */
function LoadBars({ points, max }: { points: Point[]; max: number }) {
  const recent = useMemo(() => points.slice(-90), [points]);
  if (!recent.length) return <div className={styles.barsEmpty} />;
  return (
    <div className={styles.bars}>
      {recent.map((point) => {
        const ratio = Math.max(0, Math.min(1, point.v / max));
        return (
          <span
            key={point.t}
            className={styles.bar}
            style={{
              height: `${Math.max(8, ratio * 100)}%`,
              background: percentTone(point.v),
              opacity: 0.4 + ratio * 0.6,
            }}
          />
        );
      })}
    </div>
  );
}

export function Meta({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: string;
}) {
  return (
    <div className={styles.meta}>
      <span className={styles.metaLabel}>
        {tone ? (
          <i className={styles.metaDot} style={{ background: tone }} />
        ) : null}
        {label}
      </span>
      <span className={styles.metaValue}>{value}</span>
    </div>
  );
}

export function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.readout}>
      <span className={styles.readoutLabel}>{label}</span>
      <span className={styles.readoutValue}>{value}</span>
    </div>
  );
}

export default function NodeDashboard({
  series,
  cores,
}: {
  series: Series;
  cores: number;
}) {
  const { t } = useTranslation();

  const cpu = series.cpu ?? [];
  const mem = series.mem ?? [];
  const load = series.load ?? [];
  const disk = series.disk_usage ?? [];
  const netIn = series.net_in ?? [];
  const netOut = series.net_out ?? [];

  const cpuValues = finite(cpu);
  const memValues = finite(mem);
  const diskValues = finite(disk);
  const netValues = [...finite(netIn), ...finite(netOut)];

  const cpuLatest = latestOf(cpu);
  const memLatest = latestOf(mem);
  const loadLatest = latestOf(load);
  const diskLatest = latestOf(disk);
  const netInLatest = latestOf(netIn);
  const netOutLatest = latestOf(netOut);

  const cpuPeak = cpuValues.length ? Math.max(...cpuValues) : null;
  const memPeak = memValues.length ? Math.max(...memValues) : null;
  const diskPeak = diskValues.length ? Math.max(...diskValues) : null;
  const netPeak = netValues.length ? Math.max(...netValues) : null;

  const coreCount = cores > 0 ? cores : 1;
  const loadRatio = loadLatest === null ? 0 : loadLatest / coreCount;

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
              {cpuLatest === null ? "—" : cpuLatest.toFixed(0)}
            </span>
            <span className={styles.heroUnit}>%</span>
          </div>
          <span className={styles.heroTag}>{t("cloud.metricCpu")}</span>
        </div>

        <LoadBars points={cpu} max={100} />

        <div className={styles.heroMeta}>
          <Meta
            label={t("cloud.nodeCores")}
            value={coreCount}
            tone="var(--nd-green)"
          />
          <Meta
            label={t("cloud.kpiPeak")}
            value={cpuPeak === null ? "—" : `${cpuPeak.toFixed(0)}%`}
            tone="var(--nd-red)"
          />
          <Meta
            label={t("cloud.kpiAverage")}
            value={
              averageOf(cpuValues) === null
                ? "—"
                : `${averageOf(cpuValues)!.toFixed(0)}%`
            }
            tone="var(--nd-orange)"
          />
          <Meta
            label={t("cloud.kpiSamples")}
            value={cpuValues.length}
            tone="var(--nd-track)"
          />
        </div>
      </section>

      <div className={styles.grid}>
        <section className={styles.card}>
          <span className={styles.cardLabel}>{t("cloud.metricMem")}</span>
          <div className={styles.cardBody}>
            <Gauge
              ratio={memLatest == null ? 0 : memLatest / 100}
              color={percentTone(memLatest)}
            >
              {memLatest === null ? "—" : `${memLatest.toFixed(0)}%`}
            </Gauge>
            <div className={styles.readouts}>
              <Readout
                label={t("cloud.kpiAverage")}
                value={
                  averageOf(memValues) === null
                    ? "—"
                    : `${averageOf(memValues)!.toFixed(1)}%`
                }
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
              ratio={loadLatest == null ? 0 : Math.min(1, loadRatio)}
              color={loadTone(loadLatest == null ? null : loadRatio)}
            >
              {loadLatest === null ? "—" : loadLatest.toFixed(2)}
            </Gauge>
            <div className={styles.readouts}>
              <Readout label={t("cloud.nodeCores")} value={`${coreCount}`} />
              <Readout
                label={t("cloud.nodePerCore")}
                value={loadLatest === null ? "—" : loadRatio.toFixed(2)}
              />
            </div>
          </div>
        </section>

        <section className={styles.card}>
          <span className={styles.cardLabel}>{t("cloud.metricDisk")}</span>
          <div className={styles.cardBody}>
            <Gauge
              ratio={diskLatest == null ? 0 : diskLatest / 100}
              color={percentTone(diskLatest)}
            >
              {diskLatest === null ? "—" : `${diskLatest.toFixed(0)}%`}
            </Gauge>
            <div className={styles.readouts}>
              <Readout
                label={t("cloud.kpiAverage")}
                value={
                  averageOf(diskValues) === null
                    ? "—"
                    : `${averageOf(diskValues)!.toFixed(1)}%`
                }
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
              ratio={netPeak ? (netInLatest ?? 0) / netPeak : 0}
              color="var(--nd-orange)"
              size={52}
              stroke={6}
            >
              <span className={styles.netArrow}>↓</span>
            </Gauge>
            <Gauge
              ratio={netPeak ? (netOutLatest ?? 0) / netPeak : 0}
              color="var(--nd-green)"
              size={52}
              stroke={6}
            >
              <span className={styles.netArrow}>↑</span>
            </Gauge>
            <div className={styles.readouts}>
              <Readout
                label={t("cloud.metricNetIn")}
                value={formatNet(netInLatest)}
              />
              <Readout
                label={t("cloud.metricNetOut")}
                value={formatNet(netOutLatest)}
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
