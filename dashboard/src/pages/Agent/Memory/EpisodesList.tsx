/**
 * EpisodesList.tsx — emotional diary timeline grouped by date with a detail drawer.
 *
 * Episodes do not participate in normal conversation recall; they feed proactive
 * care and weekly/monthly summaries. The timeline groups by date and shows a
 * compact intensity bar while hiding raw IDs.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Card,
  Drawer,
  Empty,
  Pagination,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { useTranslation } from "react-i18next";

import {
  memoryDashboardApi,
  type EpisodeItem,
} from "../../../api/modules/memoryDashboard";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import {
  calendarDaysAgo,
  formatServerHourMinute,
  formatServerIsoDateTime,
  formatServerYmd,
} from "../../../utils/formatMessageTime";

const PAGE_SIZE = 20;

interface Props {
  agentId: string;
}

export default function EpisodesList({ agentId }: Props) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [items, setItems] = useState<EpisodeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<EpisodeItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await memoryDashboardApi.listEpisodes(agentId, {
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setItems(r.items);
      setTotal(r.total);
    } finally {
      setLoading(false);
    }
  }, [agentId, page]);

  useEffect(() => {
    if (!agentId) return;
    void load();
  }, [agentId, load]);

  // Group by date while preserving order; consecutive same-day records share one section.
  const groups = useMemo(() => groupByDay(items, timeZone), [items, timeZone]);

  return (
    <Card size="small">
      {/* Explanation banner clarifying this does not participate in conversation recall */}
      <div
        style={{
          background: "#fff7e6",
          border: "1px solid #ffd591",
          borderRadius: 6,
          padding: "8px 12px",
          marginBottom: 12,
          fontSize: 12,
          color: "#874d00",
          lineHeight: 1.6,
        }}
      >
        💡{" "}
        {t(
          "memory.episodes.disclaimer",
          "这里记录你与 Octop 相处中的情绪和小故事。它不会用于常规对话引用，只会帮 Octop 更好地关心你，并用于周 / 月小结。",
        )}
      </div>
      {loading && items.length === 0 ? (
        <Skeleton active />
      ) : items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="episode-timeline" style={{ paddingLeft: 4 }}>
          {groups.map((g) => (
            <div key={g.label} style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "#8c8c8c",
                  margin: "8px 0 6px",
                  borderBottom: "1px solid #f0f0f0",
                  paddingBottom: 4,
                }}
              >
                📅 {g.label}
                <span style={{ marginLeft: 8, fontWeight: 400 }}>
                  ({g.items.length})
                </span>
              </div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {g.items.map((ep) => (
                  <li
                    key={ep.id}
                    onClick={() => setSelected(ep)}
                    style={{
                      display: "flex",
                      gap: 12,
                      padding: "10px 0",
                      borderBottom: "1px dashed #f5f5f5",
                      cursor: "pointer",
                      alignItems: "flex-start",
                    }}
                  >
                    {/* Left: time dot plus intensity bar */}
                    <div
                      style={{
                        flex: "0 0 56px",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-start",
                      }}
                    >
                      <div
                        style={{
                          fontSize: 11,
                          color: "#8c8c8c",
                          marginBottom: 4,
                        }}
                      >
                        {formatServerHourMinute(ep.occurred_at, timeZone)}
                      </div>
                      <IntensityBar
                        intensity={ep.intensity}
                        emotion={ep.emotion}
                      />
                    </div>
                    {/* Right: content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Space size={4} wrap>
                        <Tag color={emotionColor(ep.emotion)}>
                          {emotionLabel(ep.emotion)} · 强度 {ep.intensity}
                        </Tag>
                        {(ep.topics || []).slice(0, 3).map((topic) => (
                          <Tag key={topic}>{topic}</Tag>
                        ))}
                      </Space>
                      <div style={{ marginTop: 4, fontSize: 13 }}>
                        {ep.summary}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 12, textAlign: "right" }}>
        <Pagination
          current={page}
          pageSize={PAGE_SIZE}
          total={total}
          showSizeChanger={false}
          onChange={setPage}
        />
      </div>

      <Drawer
        title={t("memory.episodeDetail", "情绪日记详情")}
        open={!!selected}
        onClose={() => setSelected(null)}
        width={520}
      >
        {selected ? (
          <div>
            <Space size={4} wrap style={{ marginBottom: 12 }}>
              <Tag color={emotionColor(selected.emotion)}>
                {emotionLabel(selected.emotion)} · 强度 {selected.intensity}
              </Tag>
              {(selected.topics || []).map((tp) => (
                <Tag key={tp}>{tp}</Tag>
              ))}
            </Space>
            <Typography.Title level={5}>摘要</Typography.Title>
            <Typography.Paragraph>{selected.summary}</Typography.Paragraph>
            <Typography.Title level={5}>原话依据</Typography.Title>
            <Typography.Paragraph type="secondary">
              {selected.verbatim_quote}
            </Typography.Paragraph>
            {selected.people && selected.people.length > 0 ? (
              <>
                <Typography.Title level={5}>涉及的人</Typography.Title>
                <Space size={4} wrap>
                  {selected.people.map((p) => (
                    <Tag key={p}>{p}</Tag>
                  ))}
                </Space>
              </>
            ) : null}
            <Typography.Paragraph
              type="secondary"
              style={{ fontSize: 12, marginTop: 12 }}
            >
              发生于 {formatServerIsoDateTime(selected.occurred_at, timeZone)}
            </Typography.Paragraph>
          </div>
        ) : null}
      </Drawer>
    </Card>
  );
}

function emotionColor(e: string): string {
  const k = (e || "").toLowerCase();
  if (k.includes("happy") || k.includes("joy")) return "green";
  if (k.includes("sad")) return "blue";
  if (k.includes("angry") || k.includes("anger")) return "red";
  if (k.includes("surpr")) return "purple";
  if (k.includes("anxi") || k.includes("worry")) return "orange";
  return "default";
}

function emotionLabel(e: string): string {
  const k = (e || "").toLowerCase();
  if (k.includes("happy") || k.includes("joy")) return "开心";
  if (k.includes("sad")) return "难过";
  if (k.includes("angry") || k.includes("anger")) return "生气";
  if (k.includes("surpr")) return "惊讶";
  if (k.includes("anxi") || k.includes("worry")) return "焦虑";
  if (k.includes("calm") || k.includes("neutral")) return "平静";
  return e || "未分类";
}

function emotionHex(e: string): string {
  const k = (e || "").toLowerCase();
  if (k.includes("happy") || k.includes("joy")) return "#52c41a";
  if (k.includes("sad")) return "#1677ff";
  if (k.includes("angry") || k.includes("anger")) return "#ff4d4f";
  if (k.includes("surpr")) return "#722ed1";
  if (k.includes("anxi") || k.includes("worry")) return "#fa8c16";
  return "#8c8c8c";
}

interface DayGroup {
  label: string;
  items: EpisodeItem[];
}

function groupByDay(items: EpisodeItem[], timeZone: string): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const it of items) {
    const diffDays = calendarDaysAgo(it.occurred_at, timeZone);
    let label: string;
    if (diffDays === 0) label = "今天";
    else if (diffDays === 1) label = "昨天";
    else if (diffDays > 1 && diffDays < 7) label = `${diffDays} 天前`;
    else label = formatServerYmd(it.occurred_at, timeZone);

    const last = groups[groups.length - 1];
    if (last && last.label === label) {
      last.items.push(it);
    } else {
      groups.push({ label, items: [it] });
    }
  }
  return groups;
}

function IntensityBar({
  intensity,
  emotion,
}: {
  intensity: number;
  emotion: string;
}) {
  const clamped = Math.max(0, Math.min(10, intensity));
  const widthPct = (clamped / 10) * 100;
  return (
    <div
      style={{
        width: 48,
        height: 4,
        background: "#f0f0f0",
        borderRadius: 2,
        overflow: "hidden",
      }}
      title={`intensity=${intensity}`}
    >
      <div
        style={{
          width: `${widthPct}%`,
          height: "100%",
          background: emotionHex(emotion),
        }}
      />
    </div>
  );
}
