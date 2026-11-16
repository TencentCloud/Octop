import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Segmented } from "antd";
import { CloseOutlined } from "@ant-design/icons";
import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import styles from "./MetricTrendChart.module.less";

export type TrendRow = Record<string, number>;

type MetricKey = "cpu" | "mem" | "load" | "net_in" | "net_out";
type MetricKind = "percent" | "number" | "bandwidth";

const SERIES: Record<
  MetricKey,
  { color: string; gradient: string; labelKey: string }
> = {
  cpu: {
    color: "var(--sc-accent)",
    gradient: "trendCpuFill",
    labelKey: "cloud.metricCpu",
  },
  mem: {
    color: "var(--sc-muted)",
    gradient: "trendMemFill",
    labelKey: "cloud.metricMem",
  },
  load: {
    color: "var(--sc-accent)",
    gradient: "trendLoadFill",
    labelKey: "cloud.metricLoad",
  },
  net_in: {
    color: "var(--sc-accent)",
    gradient: "trendNetInFill",
    labelKey: "cloud.metricNetIn",
  },
  net_out: {
    color: "var(--sc-muted)",
    gradient: "trendNetOutFill",
    labelKey: "cloud.metricNetOut",
  },
};

type Group = {
  key: string;
  labelKey: string;
  metrics: MetricKey[];
  kind: MetricKind;
  domain: [number, number | "auto"];
  ticks?: number[];
  threshold?: number;
};

const GROUPS: Group[] = [
  {
    key: "overview",
    labelKey: "cloud.trendGroupOverview",
    metrics: ["cpu", "mem"],
    kind: "percent",
    domain: [0, 100],
    ticks: [0, 25, 50, 75, 100],
    threshold: 80,
  },
  {
    key: "load",
    labelKey: "cloud.trendGroupLoad",
    metrics: ["load"],
    kind: "number",
    domain: [0, "auto"],
  },
  {
    key: "network",
    labelKey: "cloud.trendGroupNetwork",
    metrics: ["net_in", "net_out"],
    kind: "bandwidth",
    domain: [0, "auto"],
  },
];

function formatValue(value: number, kind: MetricKind): string {
  if (!Number.isFinite(value)) return "-";
  if (kind === "percent") return `${value.toFixed(1)}%`;
  if (kind === "bandwidth") {
    if (value >= 1000) return `${(value / 1000).toFixed(2)} Gbps`;
    return `${value.toFixed(1)} Mbps`;
  }
  return value.toFixed(2);
}

function compactTick(value: number, kind: MetricKind): string {
  if (kind === "percent") return `${value}%`;
  if (kind === "bandwidth") {
    return value >= 1000
      ? `${(value / 1000).toFixed(1)}G`
      : `${Math.round(value)}`;
  }
  return `${Math.round(value * 10) / 10}`;
}

function formatTick(timestamp: number, range: string): string {
  const date = new Date(timestamp * 1000);
  const clock = date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  if (range === "1h") return clock;
  return `${date.getMonth() + 1}/${date.getDate()} ${clock}`;
}

function TrendTooltip({
  active,
  payload,
  label,
  range,
  kind,
}: {
  active?: boolean;
  payload?: Array<{
    dataKey?: string | number;
    name?: string;
    value?: number;
    color?: string;
  }>;
  label?: number;
  range: string;
  kind: MetricKind;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipTime}>
        {formatTick(Number(label), range)}
      </div>
      {payload.map((item) => (
        <div key={String(item.dataKey)} className={styles.tooltipRow}>
          <span
            className={styles.tooltipDot}
            style={{ background: item.color }}
          />
          <span className={styles.tooltipName}>{item.name}</span>
          <span className={styles.tooltipValue}>
            {formatValue(Number(item.value ?? 0), kind)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function MetricTrendChart({
  data,
  range,
  focusTs = null,
  onClearFocus,
  height = 210,
}: {
  data: TrendRow[];
  range: string;
  focusTs?: number | null;
  onClearFocus?: () => void;
  height?: number;
}) {
  const { t } = useTranslation();
  const [groupKey, setGroupKey] = useState<string>(GROUPS[0].key);
  const [zoom, setZoom] = useState<{ start: number; end: number } | null>(null);
  const [hidden, setHidden] = useState<MetricKey[]>([]);

  const group = GROUPS.find((item) => item.key === groupKey) ?? GROUPS[0];
  const dataRef = useRef(data);
  dataRef.current = data;

  const maxIndex = Math.max(0, data.length - 1);
  const startIndex = Math.min(Math.max(zoom?.start ?? 0, 0), maxIndex);
  const endIndex = Math.min(Math.max(zoom?.end ?? maxIndex, 0), maxIndex);
  const isZoomed = startIndex > 0 || endIndex < maxIndex;

  useEffect(() => {
    if (focusTs == null) {
      setZoom(null);
      return;
    }
    const rows = dataRef.current;
    if (!rows.length) return;
    let index = rows.findIndex((row) => row.t >= focusTs);
    if (index < 0) index = rows.length - 1;
    const half = 3;
    setZoom({
      start: Math.max(0, index - half),
      end: Math.min(rows.length - 1, index + half),
    });
  }, [focusTs]);

  useEffect(() => {
    setZoom(null);
  }, [groupKey]);

  const hasData = useMemo(
    () =>
      data.some((row) =>
        group.metrics.some((key) => Number.isFinite(row[key])),
      ),
    [data, group.metrics],
  );

  const latestOf = (key: MetricKey): number | null => {
    for (let index = data.length - 1; index >= 0; index -= 1) {
      const value = data[index][key];
      if (Number.isFinite(value)) return value;
    }
    return null;
  };

  const focusLabel = useMemo(() => {
    if (!isZoomed) return "";
    const from = data[startIndex]?.t;
    const to = data[endIndex]?.t;
    if (from == null || to == null) return "";
    return `${formatTick(from, range)} – ${formatTick(to, range)}`;
  }, [data, startIndex, endIndex, isZoomed, range]);

  const toggle = (key: MetricKey) => {
    setHidden((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key],
    );
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.title}>{t("cloud.trendTitle")}</span>
          <Segmented
            size="small"
            value={groupKey}
            onChange={(value) => setGroupKey(String(value))}
            options={GROUPS.map((item) => ({
              label: t(item.labelKey),
              value: item.key,
            }))}
          />
        </div>
        <div className={styles.chips}>
          {isZoomed ? (
            <button
              type="button"
              className={styles.focusChip}
              title={focusLabel}
              onClick={() => {
                setZoom(null);
                onClearFocus?.();
              }}
            >
              <span className={styles.focusRange}>{focusLabel}</span>
              <CloseOutlined className={styles.focusClose} />
            </button>
          ) : null}
          {group.metrics.map((key) => {
            const meta = SERIES[key];
            const value = latestOf(key);
            const muted = hidden.includes(key);
            return (
              <button
                key={key}
                type="button"
                className={muted ? styles.chipMuted : styles.chip}
                onClick={() => toggle(key)}
              >
                <span
                  className={styles.chipDot}
                  style={{ background: meta.color }}
                />
                <span className={styles.chipName}>{t(meta.labelKey)}</span>
                <span className={styles.chipValue}>
                  {value === null ? "-" : formatValue(value, group.kind)}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {hasData ? (
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart
            data={data}
            margin={{ top: 8, right: 8, bottom: 0, left: -14 }}
          >
            <defs>
              {(Object.keys(SERIES) as MetricKey[]).map((key) => (
                <linearGradient
                  key={SERIES[key].gradient}
                  id={SERIES[key].gradient}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor={SERIES[key].color}
                    stopOpacity={0.32}
                  />
                  <stop
                    offset="70%"
                    stopColor={SERIES[key].color}
                    stopOpacity={0.06}
                  />
                  <stop
                    offset="100%"
                    stopColor={SERIES[key].color}
                    stopOpacity={0}
                  />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid
              vertical={false}
              stroke="currentColor"
              strokeOpacity={0.07}
              strokeDasharray="4 4"
            />
            <XAxis
              dataKey="t"
              tickFormatter={(value: number) => formatTick(value, range)}
              tickLine={false}
              axisLine={false}
              fontSize={11}
              tickMargin={8}
              minTickGap={28}
              tickCount={Math.min(6, Math.max(2, data.length))}
            />
            <YAxis
              domain={group.domain}
              ticks={group.ticks}
              tickFormatter={(value: number) => compactTick(value, group.kind)}
              tickLine={false}
              axisLine={false}
              fontSize={11}
              width={46}
            />
            <Tooltip
              content={(props) => (
                <TrendTooltip
                  active={props.active}
                  payload={props.payload as never}
                  label={props.label as number}
                  range={range}
                  kind={group.kind}
                />
              )}
              cursor={{ stroke: "currentColor", strokeOpacity: 0.15 }}
            />
            {group.threshold != null ? (
              <ReferenceLine
                y={group.threshold}
                stroke="var(--sc-danger)"
                strokeDasharray="5 4"
                strokeOpacity={0.55}
                label={{
                  value: `${group.threshold}%`,
                  position: "insideTopRight",
                  fill: "var(--sc-danger)",
                  fontSize: 10,
                  opacity: 0.8,
                }}
              />
            ) : null}
            {group.metrics.map((key) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                name={t(SERIES[key].labelKey)}
                stroke={SERIES[key].color}
                strokeWidth={2}
                fill={`url(#${SERIES[key].gradient})`}
                dot={false}
                activeDot={{
                  r: 4,
                  strokeWidth: 2,
                  stroke: "var(--fn-bg-primary)",
                }}
                hide={hidden.includes(key)}
                connectNulls
              />
            ))}
            {data.length > 4 ? (
              <Brush
                dataKey="t"
                height={22}
                travellerWidth={6}
                stroke="var(--sc-accent)"
                fill="var(--sc-accent-soft)"
                startIndex={startIndex}
                endIndex={endIndex}
                tickFormatter={() => ""}
                onChange={(next: {
                  startIndex?: number;
                  endIndex?: number;
                }) => {
                  const start = Number(next?.startIndex ?? 0);
                  const end = Number(next?.endIndex ?? maxIndex);
                  if (start <= 0 && end >= maxIndex) setZoom(null);
                  else setZoom({ start, end });
                }}
              />
            ) : null}
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <div className={styles.noData}>{t("cloud.trendNoData")}</div>
      )}
    </div>
  );
}
