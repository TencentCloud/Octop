/**
 * MemoryPipelineEmpty — guided empty state for the memory tree / atom list.
 *
 * A bare <Empty> reads as "memory is broken" to users whose atoms haven't
 * been distilled yet, even though raw materials are being captured from the
 * very first conversation turn. This component checks stats_counts and, when
 * raw events exist, explains that distillation runs automatically after the
 * session goes idle — turning "it doesn't work" into "it's on its way".
 *
 * Degrades to the plain <Empty> whenever stats are unavailable (endpoint
 * missing in test mocks, request failure, older bridge), matching the
 * defensive pattern in LineageStrip.
 */

import { useEffect, useState } from "react";
import { Empty, Skeleton } from "antd";
import { useTranslation } from "react-i18next";

import {
  memoryDashboardApi,
  type StatsCounts,
} from "../../../../api/modules/memoryDashboard";

interface Props {
  agentId: string;
}

export default function MemoryPipelineEmpty({ agentId }: Props) {
  const { t } = useTranslation();
  const [counts, setCounts] = useState<StatsCounts | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setCounts(null);

    (async () => {
      try {
        if (typeof memoryDashboardApi.statsCounts !== "function") return;
        const c = await memoryDashboardApi
          .statsCounts(agentId)
          .catch(() => null);
        if (!cancelled) setCounts(c);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [agentId]);

  if (loading) {
    return <Skeleton active paragraph={{ rows: 2 }} title={false} />;
  }

  const rawCount = counts?.raw_events ?? 0;
  const pendingCount = counts?.candidates_pending ?? 0;

  if (rawCount <= 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t(
          "memory.pipeline.emptyNoRaw",
          "还没有记忆。开始对话后，系统会自动捕获素材并提炼记忆。",
        )}
      />
    );
  }

  return (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={t("memory.pipeline.emptyTitle", "记忆还在提炼中")}
    >
      <div
        style={{
          fontSize: 12,
          color: "var(--fn-text-tertiary, #8c8c8c)",
          maxWidth: 420,
          margin: "0 auto",
          lineHeight: 1.6,
        }}
      >
        {t(
          "memory.pipeline.emptyWithRaw",
          "已捕获 {{n}} 条对话记忆。记忆提炼会在会话空闲后自动运行，首批记忆通常在几轮对话后出现。",
          { n: rawCount },
        )}
        {pendingCount > 0 ? (
          <>
            {" "}
            {t(
              "memory.pipeline.emptyPendingSuffix",
              "另有 {{n}} 条候选记忆待确认，请前往「记忆沉淀」查看。",
              { n: pendingCount },
            )}
          </>
        ) : null}
      </div>
    </Empty>
  );
}
