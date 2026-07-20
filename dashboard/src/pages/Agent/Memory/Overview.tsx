import { useCallback, useEffect, useState } from "react";
import { Button, Card, Empty, Skeleton, Tooltip } from "antd";
import {
  BrainCircuit,
  Database,
  Loader2,
  RefreshCw,
  Settings2,
  Sparkles,
  Tags,
  Workflow,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import MigrateMemory from "./MigrateMemory";
import {
  memoryDashboardApi,
  type ExtractConfig,
  type StatsAtomKindsResponse,
  type StatsCounts,
  type StatsGrowthResponse,
} from "../../../api/modules/memoryDashboard";
import styles from "./Overview.module.less";

interface Props {
  agentId: string;
  onViewConversations?: () => void;
  onReviewCandidates?: () => void;
  onOpenSettings?: () => void;
}

interface PageState {
  counts: StatsCounts | null;
  kinds: StatsAtomKindsResponse | null;
  growth: StatsGrowthResponse | null;
  config: ExtractConfig | null;
  firstLoading: boolean;
  refreshing: boolean;
}

const INITIAL_STATE: PageState = {
  counts: null,
  kinds: null,
  growth: null,
  config: null,
  firstLoading: true,
  refreshing: false,
};

const KIND_COLOR: Record<string, string> = {
  Preference: "#e85d75",
  Task: "#f59e0b",
  Fact: "#3b82f6",
  Decision: "#8b5cf6",
  ConflictCandidate: "#94a3b8",
};

export default function Overview({
  agentId,
  onViewConversations,
  onReviewCandidates,
  onOpenSettings,
}: Props) {
  const { t } = useTranslation();
  const [state, setState] = useState<PageState>(INITIAL_STATE);
  // Older running API processes do not return this newly-added field.  Match
  // the backend default and only show the disabled state for an explicit false.
  const memoryEnabled = state.config?.memory_enabled !== false;

  const loadAll = useCallback(async () => {
    if (!agentId) return;
    setState((current) => ({ ...current, refreshing: true }));
    const results = await Promise.allSettled([
      memoryDashboardApi.statsCounts(agentId),
      memoryDashboardApi.statsAtomKinds(agentId),
      memoryDashboardApi.statsGrowth(agentId, 14),
      memoryDashboardApi.getExtractConfig(agentId),
    ]);
    const [counts, kinds, growth, config] = results;
    setState({
      counts: counts.status === "fulfilled" ? counts.value : null,
      kinds: kinds.status === "fulfilled" ? kinds.value : null,
      growth: growth.status === "fulfilled" ? growth.value : null,
      config: config.status === "fulfilled" ? config.value : null,
      firstLoading: false,
      refreshing: false,
    });
  }, [agentId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  return (
    <div className={styles.overview}>
      <header className={styles.overviewHero}>
        <div className={styles.overviewHeroMain}>
          <span className={styles.overviewHeroIcon}>
            <BrainCircuit size={24} />
          </span>
          <div>
            <div className={styles.overviewTitleRow}>
              <h2>{t("memory.overview.dashboardTitle", "记忆概览")}</h2>
              {!state.firstLoading && state.config ? (
                <span
                  className={
                    memoryEnabled
                      ? styles.memoryStatusOn
                      : styles.memoryStatusOff
                  }
                >
                  <i />
                  {memoryEnabled
                    ? t("memory.overview.memoryOn", "记忆运行中")
                    : t("memory.overview.memoryOff", "记忆已关闭")}
                </span>
              ) : null}
            </div>
            <p>
              {t(
                "memory.overview.dashboardSubtitle",
                "快速了解 Agent 记住了什么，以及记忆处理是否正常。",
              )}
            </p>
          </div>
        </div>
        <div className={styles.overviewActions}>
          {onOpenSettings ? (
            <Button icon={<Settings2 size={14} />} onClick={onOpenSettings}>
              {t("memory.tabs.settings", "设置")}
            </Button>
          ) : null}
          <Tooltip title={t("common.refresh", "刷新")}>
            <Button
              aria-label={t("common.refresh", "刷新")}
              icon={
                state.refreshing ? (
                  <Loader2 className={styles.spinning} size={14} />
                ) : (
                  <RefreshCw size={14} />
                )
              }
              onClick={() => void loadAll()}
              disabled={state.refreshing}
            />
          </Tooltip>
          <MigrateMemory agentId={agentId} />
        </div>
      </header>

      <div className={styles.summaryGrid}>
        <SummaryCard
          icon={<Sparkles size={18} />}
          tone="rose"
          label={t("memory.overview.atoms", "长期记忆")}
          value={state.counts?.atoms}
          delta={state.counts?.atoms_delta_7d}
          loading={state.firstLoading}
        />
        <SummaryCard
          icon={<Tags size={18} />}
          tone="violet"
          label={t("memory.overview.entities", "关键主题")}
          value={state.counts?.entities}
          delta={state.counts?.entities_delta_7d}
          loading={state.firstLoading}
        />
        <SummaryCard
          icon={<Database size={18} />}
          tone="blue"
          label={t("memory.overview.rawEvents", "对话素材")}
          value={state.counts?.raw_events}
          loading={state.firstLoading}
        />
        <SummaryCard
          icon={<Workflow size={18} />}
          tone="amber"
          label={t("memory.overview.candidatesPending", "待处理")}
          value={state.counts?.candidates_pending}
          loading={state.firstLoading}
          warn={(state.counts?.candidates_pending ?? 0) > 0}
        />
      </div>

      <PipelineCard
        loading={state.firstLoading}
        counts={state.counts}
        onViewConversations={onViewConversations}
        onReviewCandidates={onReviewCandidates}
        t={t}
      />

      <div className={styles.overviewCharts}>
        <Card
          className={styles.overviewChartCard}
          title={t("memory.overview.growthTitle", "近 14 天记忆增长")}
        >
          {state.firstLoading && !state.growth ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : !state.growth || state.growth.series.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("memory.overview.growthEmpty", "近 14 天暂无新增")}
            />
          ) : (
            <div className={styles.growthChart}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={state.growth.series}
                  margin={{ top: 8, right: 8, bottom: 0, left: -20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(date: string) => date.slice(5)}
                  />
                  <YAxis allowDecimals={false} />
                  <ChartTooltip
                    formatter={(value) => [
                      value,
                      t("memory.overview.atoms", "长期记忆"),
                    ]}
                  />
                  <Bar dataKey="atoms" fill="#e85d75" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card
          className={styles.overviewChartCard}
          title={t("memory.overview.kindsTitle", "记忆类型")}
        >
          {state.firstLoading && !state.kinds ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : !state.kinds || state.kinds.series.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("memory.overview.kindsEmpty", "暂无记忆类型数据")}
            />
          ) : (
            <div className={styles.kindChart}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={state.kinds.series}
                    dataKey="count"
                    nameKey="kind"
                    innerRadius={48}
                    outerRadius={76}
                    paddingAngle={3}
                    stroke="none"
                  >
                    {state.kinds.series.map((entry) => (
                      <Cell
                        key={entry.kind}
                        fill={KIND_COLOR[entry.kind] ?? "#94a3b8"}
                      />
                    ))}
                  </Pie>
                  <ChartTooltip
                    formatter={(value, name) => [
                      value,
                      kindLabel(String(name), t),
                    ]}
                  />
                  <Legend formatter={(value) => kindLabel(String(value), t)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function SummaryCard({
  icon,
  tone,
  label,
  value,
  delta,
  loading,
  warn,
}: {
  icon: React.ReactNode;
  tone: "rose" | "violet" | "blue" | "amber";
  label: string;
  value: number | undefined;
  delta?: number;
  loading: boolean;
  warn?: boolean;
}) {
  return (
    <div className={`${styles.summaryCard} ${styles[`summary_${tone}`]}`}>
      <span className={styles.summaryIcon}>{icon}</span>
      <div className={styles.summaryContent}>
        <span>{label}</span>
        {loading && value === undefined ? (
          <Skeleton.Input active size="small" />
        ) : (
          <strong className={warn ? styles.summaryWarn : undefined}>
            {value ?? "-"}
          </strong>
        )}
      </div>
      {delta !== undefined && delta > 0 ? (
        <span className={styles.summaryDelta}>+{delta} / 7d</span>
      ) : null}
    </div>
  );
}

function PipelineCard({
  loading,
  counts,
  onViewConversations,
  onReviewCandidates,
  t,
}: {
  loading: boolean;
  counts: StatsCounts | null;
  onViewConversations?: () => void;
  onReviewCandidates?: () => void;
  t: TFunction;
}) {
  if (loading && !counts) {
    return (
      <Card className={styles.pipelineCard}>
        <Skeleton active paragraph={{ rows: 2 }} title={false} />
      </Card>
    );
  }
  if (!counts) return null;

  const raw = counts.raw_events ?? 0;
  const pending = counts.candidates_pending ?? 0;
  const atoms = counts.atoms ?? 0;
  const hint =
    raw === 0
      ? t(
          "memory.pipeline.hintNoRaw",
          "开始对话后，系统会自动捕获素材并提炼记忆。",
        )
      : atoms === 0
      ? t(
          "memory.pipeline.hintDistilling",
          "已捕获 {{n}} 条对话素材，首批长期记忆通常会在几轮对话后出现。",
          { n: raw },
        )
      : t(
          "memory.pipeline.hintNormal",
          "对话素材会自动提炼为候选内容，确认后成为可召回的长期记忆。",
        );

  return (
    <Card className={styles.pipelineCard}>
      <div className={styles.pipelineHeader}>
        <span>
          <Workflow size={16} />
          {t("memory.pipeline.title", "记忆处理进度")}
        </span>
        <small>{hint}</small>
      </div>
      <div className={styles.pipelineRow}>
        <PipelineStage
          label={t("memory.pipeline.stageRaw", "对话素材")}
          value={raw}
          onClick={onViewConversations}
        />
        <span className={styles.pipelineConnector} />
        <PipelineStage
          label={t("memory.pipeline.stagePending", "待处理")}
          value={pending}
          onClick={onReviewCandidates}
          warn={pending > 0}
        />
        <span className={styles.pipelineConnector} />
        <PipelineStage
          label={t("memory.pipeline.stageAtoms", "长期记忆")}
          value={atoms}
        />
      </div>
    </Card>
  );
}

function PipelineStage({
  label,
  value,
  onClick,
  warn,
}: {
  label: string;
  value: number;
  onClick?: () => void;
  warn?: boolean;
}) {
  return (
    <button
      type="button"
      className={`${styles.pipelineStage} ${
        onClick ? styles.pipelineStageClickable : ""
      } ${warn ? styles.pipelineStageWarn : ""}`}
      onClick={onClick}
      disabled={!onClick}
    >
      <strong>{value}</strong>
      <span>{label}</span>
    </button>
  );
}

function kindLabel(kind: string, t: TFunction): string {
  const labels: Record<string, string> = {
    Fact: t("memory.kind.fact", "事实"),
    Decision: t("memory.kind.decision", "决定"),
    Task: t("memory.kind.task", "任务"),
    Preference: t("memory.kind.preference", "偏好"),
    ConflictCandidate: t("memory.kind.conflict", "可能冲突"),
  };
  return labels[kind] ?? kind;
}
