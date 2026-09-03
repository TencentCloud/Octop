import { useTranslation } from "react-i18next";
import { type TrajectoryMetrics } from "../../../api/modules/trajectory";
import { formatDurationMs, visibleMetrics } from "../utils/trajectoryModel";
import styles from "./TrajectoryMetricsBar.module.less";

interface TrajectoryMetricsBarProps {
  agentId: string;
  threadId: string;
  metrics: TrajectoryMetrics | null;
}

const METRIC_LABEL: Record<
  keyof TrajectoryMetrics,
  { key: string; fallback: string }
> = {
  turns: { key: "chat.trajectoryMetricTurns", fallback: "Turns" },
  steps: { key: "chat.trajectoryMetricSteps", fallback: "Steps" },
  llm_duration_ms: {
    key: "chat.trajectoryMetricLlmMs",
    fallback: "LLM",
  },
  tool_duration_ms: {
    key: "chat.trajectoryMetricToolMs",
    fallback: "Tool call",
  },
  ttft_avg_ms: { key: "chat.trajectoryMetricTtft", fallback: "TTFT avg" },
  tok_per_s: { key: "chat.trajectoryMetricTokPerS", fallback: "tok/s" },
  cache_hit_ratio: {
    key: "chat.trajectoryMetricCacheHit",
    fallback: "Cache hit",
  },
  input_tokens: { key: "chat.trajectoryMetricInputTokens", fallback: "Input" },
  output_tokens: {
    key: "chat.trajectoryMetricOutputTokens",
    fallback: "Output",
  },
  cache_read_tokens: {
    key: "chat.trajectoryMetricCacheRead",
    fallback: "Cache read",
  },
};

function formatTokenCount(value: number): string {
  if (value >= 1000) {
    const kilo = value / 1000;
    return `${kilo >= 10 ? Math.round(kilo) : kilo.toFixed(1)}k`;
  }
  return String(Math.round(value));
}

function formatMetric(key: keyof TrajectoryMetrics, value: number): string {
  if (key === "cache_hit_ratio") {
    return `${Math.round(value * 100)}%`;
  }
  if (key.endsWith("_ms")) {
    return formatDurationMs(value);
  }
  if (
    key === "input_tokens" ||
    key === "output_tokens" ||
    key === "cache_read_tokens"
  ) {
    return formatTokenCount(value);
  }
  if (key === "tok_per_s") {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(1);
}

function chipText(
  key: keyof TrajectoryMetrics,
  value: number,
  label: string,
): string {
  if (key === "turns" || key === "steps") {
    return `${formatMetric(key, value)} ${label.toLowerCase()}`;
  }
  if (key === "tok_per_s") {
    return `${formatMetric(key, value)} ${label}`;
  }
  if (key === "cache_hit_ratio") {
    return `${label} ${formatMetric(key, value)}`;
  }
  return `${label} ${formatMetric(key, value)}`;
}

export default function TrajectoryMetricsBar({
  metrics,
}: TrajectoryMetricsBarProps) {
  const { t } = useTranslation();
  const entries = metrics ? visibleMetrics(metrics) : [];

  return (
    <div
      className={styles.root}
      aria-label={t("chat.trajectoryMetrics", "Session metrics")}
    >
      <div className={styles.chips}>
        {entries.map((entry, index) => {
          const label = METRIC_LABEL[entry.key];
          const text = chipText(
            entry.key,
            entry.value,
            t(label.key, label.fallback),
          );
          return (
            <span key={entry.key} className={styles.chipGroup}>
              {index > 0 ? (
                <span className={styles.sep} aria-hidden>
                  ·
                </span>
              ) : null}
              <span className={styles.chip} data-metric={entry.key}>
                {text}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
