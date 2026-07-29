/**
 * Token Usage — account-level analytics.
 *
 * Views (peer Segmented): summary | by day | by expert | by model.
 * Summary composes totals + donut/pie charts from existing
 * ``GET /api/usage/summary`` granularities (no backend changes).
 * Dimension views: stacked bar + sortable table.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Select, Spin, Table, Empty, Tag, Segmented } from "antd";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { request } from "../../../api/request";
import { useAgent } from "../../../context/AgentContext";
import styles from "./index.module.less";

interface UsageBucket {
  key: string;
  label: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  turns: number;
}

interface UsageSummary {
  window: string;
  granularity: string;
  range_start: number;
  range_end: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  turns: number;
  avg_per_turn: number;
  buckets: UsageBucket[];
}

type ViewMode = "summary" | "by_day" | "by_agent" | "by_model";
type DimGranularity = Exclude<ViewMode, "summary">;

const CHART_COLORS = [
  "#4f6ef7",
  "#a06ef7",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#06b6d4",
  "#ec4899",
  "#84cc16",
  "#64748b",
  "#8b5cf6",
];

const IO_COLORS = {
  input: "#4f6ef7",
  output: "#a06ef7",
};

function formatNumber(n: number): string {
  return n.toLocaleString();
}

function StatBlock({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className={styles.statBlock}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value}</div>
    </div>
  );
}

function bucketColumnTitle(
  granularity: DimGranularity,
  t: (key: string) => string,
): string {
  if (granularity === "by_day") return t("tokenUsage.date");
  if (granularity === "by_agent") return t("tokenUsage.expert");
  return t("tokenUsage.model");
}

function resolveAgentLabels(
  buckets: UsageBucket[],
  agentNameById: Map<string, string>,
): UsageBucket[] {
  return buckets.map((b) => ({
    ...b,
    label: agentNameById.get(b.key) ?? b.label ?? b.key,
  }));
}

function toPieData(buckets: UsageBucket[], limit = 8) {
  const sorted = [...buckets].sort((a, b) => b.total_tokens - a.total_tokens);
  if (sorted.length <= limit) {
    return sorted.map((b) => ({
      name: b.label,
      value: b.total_tokens,
      turns: b.turns,
    }));
  }
  const head = sorted.slice(0, limit - 1);
  const rest = sorted.slice(limit - 1);
  const otherValue = rest.reduce((s, b) => s + b.total_tokens, 0);
  const otherTurns = rest.reduce((s, b) => s + b.turns, 0);
  return [
    ...head.map((b) => ({
      name: b.label,
      value: b.total_tokens,
      turns: b.turns,
    })),
    { name: "…", value: otherValue, turns: otherTurns },
  ];
}

function fetchSummary(
  windowKey: string,
  granularity: string,
  agentFilter: string | "all",
): Promise<UsageSummary> {
  const params = new URLSearchParams({ window: windowKey, granularity });
  if (agentFilter !== "all") {
    params.set("agent_id", agentFilter);
  }
  return request<UsageSummary>(`/usage/summary?${params}`);
}

function DonutCard({
  title,
  data,
  emptyText,
  colors = CHART_COLORS,
}: {
  title: string;
  data: { name: string; value: number }[];
  emptyText: string;
  colors?: string[] | Record<string, string>;
}) {
  const colorFor = (name: string, index: number) => {
    if (Array.isArray(colors)) return colors[index % colors.length];
    return colors[name] ?? CHART_COLORS[index % CHART_COLORS.length];
  };

  return (
    <Card size="small" title={title} className={styles.chartCard}>
      {data.length === 0 || data.every((d) => d.value === 0) ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
      ) : (
        <div className={styles.chartArea}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                innerRadius="42%"
                outerRadius="68%"
                paddingAngle={2}
                stroke="none"
              >
                {data.map((entry, i) => (
                  <Cell key={entry.name} fill={colorFor(entry.name, i)} />
                ))}
              </Pie>
              <RechartsTooltip
                formatter={(value) => formatNumber(Number(value ?? 0))}
                contentStyle={{
                  background: "var(--fn-bg-elevated)",
                  border: "1px solid var(--fn-border-secondary)",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              />
              <Legend
                wrapperStyle={{ fontSize: 12 }}
                formatter={(value) => (
                  <span style={{ color: "var(--fn-text-secondary)" }}>
                    {value}
                  </span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

function SummaryView({
  totals,
  byExpert,
  byModel,
  byDay,
  isMobile,
}: {
  totals: UsageSummary;
  byExpert: UsageBucket[];
  byModel: UsageBucket[];
  byDay: UsageBucket[];
  isMobile: boolean;
}) {
  const { t } = useTranslation();

  const ioData = useMemo(
    () => [
      { name: t("tokenUsage.input"), value: totals.input_tokens },
      { name: t("tokenUsage.output"), value: totals.output_tokens },
    ],
    [totals.input_tokens, totals.output_tokens, t],
  );

  const expertPie = useMemo(() => toPieData(byExpert), [byExpert]);
  const modelPie = useMemo(() => toPieData(byModel), [byModel]);
  const dayBars = useMemo(() => [...byDay].reverse().slice(-14), [byDay]);

  return (
    <div className={styles.summaryBody}>
      <div
        className={styles.statsGrid}
        style={{
          gridTemplateColumns: isMobile
            ? "repeat(2, minmax(0, 1fr))"
            : "repeat(5, minmax(0, 1fr))",
        }}
      >
        <StatBlock
          label={t("tokenUsage.totalTokens")}
          value={formatNumber(totals.total_tokens)}
        />
        <StatBlock
          label={t("tokenUsage.input")}
          value={formatNumber(totals.input_tokens)}
        />
        <StatBlock
          label={t("tokenUsage.output")}
          value={formatNumber(totals.output_tokens)}
        />
        <StatBlock label={t("tokenUsage.turns")} value={totals.turns} />
        <StatBlock
          label={t("tokenUsage.avgPerTurn")}
          value={formatNumber(totals.avg_per_turn)}
        />
      </div>

      <div
        className={styles.pieGrid}
        style={{
          gridTemplateColumns: isMobile ? "1fr" : "repeat(3, minmax(0, 1fr))",
        }}
      >
        <DonutCard
          title={t("tokenUsage.ioBreakdown")}
          data={ioData}
          emptyText={t("tokenUsage.noRecordsInRange")}
          colors={{
            [t("tokenUsage.input")]: IO_COLORS.input,
            [t("tokenUsage.output")]: IO_COLORS.output,
          }}
        />
        <DonutCard
          title={t("tokenUsage.expertBreakdown")}
          data={expertPie}
          emptyText={t("tokenUsage.noRecordsInRange")}
        />
        <DonutCard
          title={t("tokenUsage.modelBreakdown")}
          data={modelPie}
          emptyText={t("tokenUsage.noRecordsInRange")}
        />
      </div>

      <Card
        size="small"
        title={t("tokenUsage.dailyTrend")}
        className={`${styles.chartCard} ${styles.trendCard}`}
      >
        {dayBars.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t("tokenUsage.noRecordsInRange")}
            style={{ padding: "24px 0" }}
          />
        ) : (
          <div className={styles.chartArea}>
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <BarChart
                data={dayBars}
                margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--fn-border-secondary)"
                />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 11 }}
                  interval="preserveStartEnd"
                  tickLine={false}
                  axisLine={false}
                  height={24}
                />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <RechartsTooltip
                  contentStyle={{
                    background: "var(--fn-bg-elevated)",
                    border: "1px solid var(--fn-border-secondary)",
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                />
                <Bar
                  dataKey="input_tokens"
                  stackId="a"
                  fill={IO_COLORS.input}
                  name={t("tokenUsage.input")}
                />
                <Bar
                  dataKey="output_tokens"
                  stackId="a"
                  fill={IO_COLORS.output}
                  name={t("tokenUsage.output")}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  );
}

function DimensionView({
  granularity,
  buckets,
  totals,
  isMobile,
}: {
  granularity: DimGranularity;
  buckets: UsageBucket[];
  totals: UsageSummary;
  isMobile: boolean;
}) {
  const { t } = useTranslation();

  const chartBuckets = useMemo(() => {
    if (granularity === "by_day") return [...buckets].reverse();
    return buckets.slice(0, 20);
  }, [buckets, granularity]);

  const pieData = useMemo(
    () =>
      granularity === "by_day" ? [] : toPieData(buckets, isMobile ? 6 : 10),
    [buckets, granularity, isMobile],
  );

  return (
    <div className={styles.summaryBody}>
      <div
        className={styles.statsGrid}
        style={{
          gridTemplateColumns: isMobile
            ? "repeat(2, minmax(0, 1fr))"
            : "repeat(5, minmax(0, 1fr))",
        }}
      >
        <StatBlock
          label={t("tokenUsage.totalTokens")}
          value={formatNumber(totals.total_tokens)}
        />
        <StatBlock
          label={t("tokenUsage.input")}
          value={formatNumber(totals.input_tokens)}
        />
        <StatBlock
          label={t("tokenUsage.output")}
          value={formatNumber(totals.output_tokens)}
        />
        <StatBlock label={t("tokenUsage.turns")} value={totals.turns} />
        <StatBlock
          label={t("tokenUsage.avgPerTurn")}
          value={formatNumber(totals.avg_per_turn)}
        />
      </div>

      {granularity !== "by_day" && pieData.length > 0 && (
        <div
          className={styles.dimChartRow}
          style={{
            gridTemplateColumns: isMobile ? "1fr" : "1fr 1.4fr",
          }}
        >
          <DonutCard
            title={
              granularity === "by_agent"
                ? t("tokenUsage.expertBreakdown")
                : t("tokenUsage.modelBreakdown")
            }
            data={pieData}
            emptyText={t("tokenUsage.noRecordsInRange")}
          />
          <Card
            size="small"
            title={t("tokenUsage.ioBarChart")}
            className={styles.chartCard}
          >
            <div className={styles.chartArea}>
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <BarChart
                  data={chartBuckets}
                  margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--fn-border-secondary)"
                  />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11 }}
                    interval="preserveStartEnd"
                    tickLine={false}
                    axisLine={false}
                    height={24}
                  />
                  <YAxis tick={{ fontSize: 11 }} width={48} />
                  <RechartsTooltip
                    contentStyle={{
                      background: "var(--fn-bg-elevated)",
                      border: "1px solid var(--fn-border-secondary)",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                  />
                  <Bar
                    dataKey="input_tokens"
                    stackId="a"
                    fill={IO_COLORS.input}
                    name={t("tokenUsage.input")}
                  />
                  <Bar
                    dataKey="output_tokens"
                    stackId="a"
                    fill={IO_COLORS.output}
                    name={t("tokenUsage.output")}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      )}

      {granularity === "by_day" && buckets.length > 0 && (
        <Card
          size="small"
          className={`${styles.chartCard} ${styles.trendCard}`}
        >
          <div className={styles.chartArea}>
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <BarChart
                data={chartBuckets}
                margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--fn-border-secondary)"
                />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 11 }}
                  interval="preserveStartEnd"
                  tickLine={false}
                  axisLine={false}
                  height={24}
                />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <RechartsTooltip
                  contentStyle={{
                    background: "var(--fn-bg-elevated)",
                    border: "1px solid var(--fn-border-secondary)",
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                />
                <Bar
                  dataKey="input_tokens"
                  stackId="a"
                  fill={IO_COLORS.input}
                  name={t("tokenUsage.input")}
                />
                <Bar
                  dataKey="output_tokens"
                  stackId="a"
                  fill={IO_COLORS.output}
                  name={t("tokenUsage.output")}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      <Card
        size="small"
        title={t("tokenUsage.detail")}
        className={`${styles.chartCard} ${styles.dimTableCard}`}
        styles={{ body: { padding: isMobile ? 0 : 16 } }}
      >
        {buckets.length === 0 ? (
          <Empty
            description={t("tokenUsage.noRecordsInRange")}
            style={{ padding: isMobile ? "20px 0" : undefined }}
          />
        ) : isMobile ? (
          <div>
            {buckets.map((b) => (
              <div key={b.key} className={styles.mobileRow}>
                <div className={styles.mobileRowTop}>
                  <Tag style={{ margin: 0 }}>{b.label}</Tag>
                  <span className={styles.mobileTotal}>
                    {formatNumber(b.total_tokens)}
                  </span>
                </div>
                <div className={styles.mobileMeta}>
                  <span>
                    {t("tokenUsage.input")} {formatNumber(b.input_tokens)}
                  </span>
                  <span>
                    {t("tokenUsage.output")} {formatNumber(b.output_tokens)}
                  </span>
                  <span>{t("tokenUsage.turnsCount", { count: b.turns })}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Table<UsageBucket>
            rowKey="key"
            size="small"
            pagination={false}
            dataSource={buckets}
            scroll={{ x: "max-content" }}
            columns={[
              {
                title: bucketColumnTitle(granularity, t),
                dataIndex: "label",
                fixed: "left",
                width: 160,
                render: (v) => <Tag>{v}</Tag>,
              },
              {
                title: t("tokenUsage.input"),
                dataIndex: "input_tokens",
                render: formatNumber,
                sorter: (a, b) => a.input_tokens - b.input_tokens,
                align: "right",
              },
              {
                title: t("tokenUsage.output"),
                dataIndex: "output_tokens",
                render: formatNumber,
                sorter: (a, b) => a.output_tokens - b.output_tokens,
                align: "right",
              },
              {
                title: t("tokenUsage.total"),
                dataIndex: "total_tokens",
                render: formatNumber,
                sorter: (a, b) => a.total_tokens - b.total_tokens,
                defaultSortOrder: "descend",
                align: "right",
              },
              {
                title: t("tokenUsage.turns"),
                dataIndex: "turns",
                sorter: (a, b) => a.turns - b.turns,
                align: "right",
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
}

export default function TokenUsagePage() {
  const { t } = useTranslation();
  const { agents } = useAgent();
  const isMobile = useIsMobile();
  const [windowKey, setWindowKey] = useState("last_30d");
  const [view, setView] = useState<ViewMode>("summary");
  const [agentFilter, setAgentFilter] = useState<string | "all">("all");

  const [totals, setTotals] = useState<UsageSummary | null>(null);
  const [dimBuckets, setDimBuckets] = useState<UsageBucket[]>([]);
  const [summaryExpert, setSummaryExpert] = useState<UsageBucket[]>([]);
  const [summaryModel, setSummaryModel] = useState<UsageBucket[]>([]);
  const [summaryDay, setSummaryDay] = useState<UsageBucket[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const agentNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of agents) {
      map.set(a.agent_id, a.name);
    }
    return map;
  }, [agents]);

  const windowOptions = useMemo(
    () => [
      { value: "today", label: t("tokenUsage.today") },
      { value: "yesterday", label: t("tokenUsage.yesterday") },
      { value: "last_7d", label: t("tokenUsage.last7d") },
      { value: "last_30d", label: t("tokenUsage.last30d") },
      { value: "all", label: t("tokenUsage.allTime") },
    ],
    [t],
  );

  const agentOptions = useMemo(
    () => [
      { value: "all", label: t("tokenUsage.allExperts") },
      ...agents.map((a) => ({ value: a.agent_id, label: a.name })),
    ],
    [agents, t],
  );

  const viewOptions = useMemo(
    () => [
      { value: "summary", label: t("tokenUsage.summary") },
      { value: "by_day", label: t("tokenUsage.byDay") },
      { value: "by_agent", label: t("tokenUsage.byExpert") },
      { value: "by_model", label: t("tokenUsage.byModel") },
    ],
    [t],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (view === "summary") {
        const [expertRes, modelRes, dayRes] = await Promise.all([
          fetchSummary(windowKey, "by_agent", agentFilter),
          fetchSummary(windowKey, "by_model", agentFilter),
          fetchSummary(windowKey, "by_day", agentFilter),
        ]);
        setTotals(expertRes);
        setSummaryExpert(resolveAgentLabels(expertRes.buckets, agentNameById));
        setSummaryModel(modelRes.buckets);
        setSummaryDay(dayRes.buckets);
        setDimBuckets([]);
      } else {
        const res = await fetchSummary(windowKey, view, agentFilter);
        setTotals(res);
        const buckets =
          view === "by_agent"
            ? resolveAgentLabels(res.buckets, agentNameById)
            : res.buckets;
        setDimBuckets(buckets);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [view, windowKey, agentFilter, agentNameById]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <PageShell
      title={t("pageShell.tokenUsage.title")}
      subtitle={t("pageShell.tokenUsage.subtitle")}
      fill
    >
      <div className={styles.page}>
        <div className={styles.toolbar}>
          <div className={styles.toolbarViews}>
            <Segmented
              value={view}
              onChange={(v) => setView(v as ViewMode)}
              options={viewOptions}
              size={isMobile ? "small" : "middle"}
            />
          </div>
          <div className={styles.toolbarFilters}>
            <Select
              value={windowKey}
              onChange={setWindowKey}
              className={styles.toolbarFilterSelect}
              style={{ width: isMobile ? undefined : 140 }}
              options={windowOptions}
            />
            <Select
              value={agentFilter}
              onChange={(v) => setAgentFilter(v)}
              className={styles.toolbarFilterSelect}
              style={{ width: isMobile ? undefined : 200 }}
              options={agentOptions}
            />
          </div>
        </div>

        <div className={styles.content}>
          {error && (
            <Card
              size="small"
              style={{ borderColor: "var(--fn-color-error)", marginBottom: 12 }}
            >
              <span style={{ color: "var(--fn-color-error)" }}>{error}</span>
            </Card>
          )}

          {loading && !totals ? (
            <div className={styles.loadingWrap}>
              <Spin />
            </div>
          ) : totals ? (
            view === "summary" ? (
              <SummaryView
                totals={totals}
                byExpert={summaryExpert}
                byModel={summaryModel}
                byDay={summaryDay}
                isMobile={isMobile}
              />
            ) : (
              <DimensionView
                granularity={view}
                buckets={dimBuckets}
                totals={totals}
                isMobile={isMobile}
              />
            )
          ) : null}
        </div>
      </div>
    </PageShell>
  );
}
