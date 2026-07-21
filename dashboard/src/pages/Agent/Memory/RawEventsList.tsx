/**
 * RawEventsList.tsx — paginated view of L0 raw events (captured conversation
 * material). This is the evidence layer the distillation pipeline reads; showing
 * it reassures users that material is being captured even before atoms exist.
 *
 * Note: raw-event counts do NOT map 1:1 to the Conversations tab — capture
 * filters short / tool / echo messages and aggregates across users. See the
 * pipeline card hint on the Overview tab.
 */

import { useCallback, useEffect, useState } from "react";
import { Input, Select, Space, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  memoryDashboardApi,
  type ListRawEventsBody,
  type RawEventItem,
} from "../../../api/modules/memoryDashboard";
import MemoryLayerView from "./shared/MemoryLayerView";
import MemoryPipelineEmpty from "./shared/MemoryPipelineEmpty";

const PAGE_SIZE = 20;

const EVENT_TYPE_OPTIONS: {
  value: string;
  labelKey: string;
  fallback: string;
}[] = [
  { value: "", labelKey: "memory.raw.typeAll", fallback: "全部类型" },
  {
    value: "user_message",
    labelKey: "memory.raw.typeUser",
    fallback: "用户消息",
  },
  {
    value: "assistant_message",
    labelKey: "memory.raw.typeAssistant",
    fallback: "AI 回复",
  },
];

interface Props {
  agentId: string;
}

function eventTypeLabel(type: string, t: TFunction): string {
  switch (type) {
    case "user_message":
      return t("memory.raw.typeUser", "用户消息");
    case "assistant_message":
      return t("memory.raw.typeAssistant", "AI 回复");
    case "tool_call":
      return t("memory.raw.typeToolCall", "工具调用");
    case "tool_result":
      return t("memory.raw.typeToolResult", "工具结果");
    default:
      return type;
  }
}

function eventTypeColor(type: string): string | undefined {
  if (type === "user_message") return "blue";
  if (type === "assistant_message") return "green";
  return undefined;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export default function RawEventsList({ agentId }: Props) {
  const { t } = useTranslation();
  const [items, setItems] = useState<RawEventItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [eventType, setEventType] = useState<string>("");
  const [query, setQuery] = useState<string>("");
  const [selected, setSelected] = useState<RawEventItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const body: ListRawEventsBody = {
      offset: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    };
    if (eventType) body.event_type = eventType;
    if (query.trim()) body.query = query.trim();
    try {
      const r = await memoryDashboardApi.listRawEvents(agentId, body);
      setItems(r.items);
      setTotal(r.total);
    } finally {
      setLoading(false);
    }
  }, [agentId, page, eventType, query]);

  useEffect(() => {
    if (!agentId) return;
    void load();
  }, [agentId, load]);

  const toolbar = (
    <>
      <span style={{ color: "#595959" }}>
        {t("memory.raw.typeFilter", "类型")}:
      </span>
      <Select
        style={{ width: 140 }}
        value={eventType}
        onChange={(v) => {
          setEventType(v);
          setPage(1);
        }}
        options={EVENT_TYPE_OPTIONS.map((o) => ({
          value: o.value,
          label: t(o.labelKey, o.fallback),
        }))}
      />
      <Input.Search
        allowClear
        style={{ width: 220 }}
        placeholder={t("memory.raw.searchPlaceholder", "搜索素材内容")}
        onSearch={(v) => {
          setQuery(v);
          setPage(1);
        }}
      />
    </>
  );

  const noFilterActive = !eventType && !query.trim();

  return (
    <MemoryLayerView<RawEventItem>
      toolbar={toolbar}
      items={items}
      total={total}
      page={page}
      pageSize={PAGE_SIZE}
      onPageChange={setPage}
      loading={loading}
      keyOf={(e) => e.id}
      selected={selected}
      onItemClick={setSelected}
      onCloseDrawer={() => setSelected(null)}
      drawerTitle={t("memory.raw.detailTitle", "素材详情")}
      drawerWidth={520}
      emptyContent={
        noFilterActive ? <MemoryPipelineEmpty agentId={agentId} /> : undefined
      }
      renderItem={(e) => (
        <div>
          <Space size={4}>
            <Tag color={eventTypeColor(e.event_type)}>
              {eventTypeLabel(e.event_type, t)}
            </Tag>
          </Space>
          <div
            style={{
              marginTop: 4,
              fontSize: 13,
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            {e.content}
          </div>
          <div style={{ marginTop: 2, fontSize: 12, color: "#8c8c8c" }}>
            {formatTime(e.timestamp)}
          </div>
        </div>
      )}
      renderDrawer={(e) => (
        <div>
          <Space size={8} wrap style={{ marginBottom: 12 }}>
            <Tag color={eventTypeColor(e.event_type)}>
              {eventTypeLabel(e.event_type, t)}
            </Tag>
          </Space>

          <Typography.Title level={5}>
            {t("memory.raw.content", "内容")}
          </Typography.Title>
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>
            {e.content}
          </Typography.Paragraph>

          <Typography.Paragraph
            type="secondary"
            style={{ fontSize: 12, marginTop: 16 }}
          >
            {t("memory.raw.capturedAt", "捕获于")} {formatTime(e.timestamp)}
          </Typography.Paragraph>
        </div>
      )}
    />
  );
}
