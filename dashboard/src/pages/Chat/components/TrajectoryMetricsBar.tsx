import { useTranslation } from "react-i18next";
import { type TrajectoryMetrics } from "../../../api/modules/trajectory";
import { visibleMetrics } from "../utils/trajectoryModel";
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
  turns: { key: "chat.dockTrajectoryMetricTurns", fallback: "Turns" },
  steps: { key: "chat.dockTrajectoryMetricSteps", fallback: "Steps" },
  llm_duration_ms: {
    key: "chat.dockTrajectoryMetricLlmMs",
    fallback: "LLM",
  },
  tool_duration_ms: {
    key: "chat.dockTrajectoryMetricToolMs",
    fallback: "Tools",
  },
  ttft_avg_ms: { key: "chat.dockTrajectoryMetricTtft", fallback: "TTFT" },
  tok_per_s: { key: "chat.dockTrajectoryMetricTokPerS", fallback: "tok/s" },
  cache_hit_ratio: {
    key: "chat.dockTrajectoryMetricCacheHit",
    fallback: "Cache",
  },
  input_tokens: { key: "chat.dockTrajectoryMetricInputTokens", fallback: "In" },
  output_tokens: {
    key: "chat.dockTrajectoryMetricOutputTokens",
    fallback: "Out",
  },
  cache_read_tokens: {
    key: "chat.dockTrajectoryMetricCacheRead",
    fallback: "Cache read",
  },
};

function formatMetric(key: keyof TrajectoryMetrics, value: number): string {
  if (key === "cache_hit_ratio") {
    return `${Math.round(value * 100)}%`;
  }
  if (key.endsWith("_ms")) {
    return `${Math.round(value)}ms`;
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(1);
}

export default function TrajectoryMetricsBar({
  metrics,
}: TrajectoryMetricsBarProps) {
  const { t } = useTranslation();
  const entries = metrics ? visibleMetrics(metrics) : [];

  return (
    <div
      className={styles.root}
      aria-label={t("chat.dockTrajectoryMetrics", "Session metrics")}
    >
      <div className={styles.chips}>
        {entries.map((entry) => {
          const label = METRIC_LABEL[entry.key];
          return (
            <span
              key={entry.key}
              className={styles.chip}
              data-metric={entry.key}
            >
              <span className={styles.label}>
                {t(label.key, label.fallback)}
              </span>
              <span className={styles.value}>
                {formatMetric(entry.key, entry.value)}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
