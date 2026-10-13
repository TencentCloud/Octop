/**
 * LineageStrip — source-conversation quote block inside the Atom drawer.
 *
 * The consolidated view always shows a user-facing quote. Full lineage such as
 * candidate / raw_event JSON should be inspected directly from SQLite.
 */

import { useEffect, useState } from "react";
import { Skeleton, Typography } from "antd";
import { useTranslation } from "react-i18next";

import {
  memoryDashboardApi,
  type AtomItem,
  type CandidateItem,
  type JournalItem,
} from "../../../../api/modules/memoryDashboard";

interface RawEventShape {
  id?: string;
  content?: string;
  text?: string;
  event_type?: string;
  [k: string]: unknown;
}

interface Props {
  agentId: string;
  atom: AtomItem;
}

export default function LineageStrip({ agentId, atom }: Props) {
  const { t } = useTranslation();
  const [rawEvent, setRawEvent] = useState<RawEventShape | null>(null);
  const [correction, setCorrection] = useState<JournalItem | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setRawEvent(null);
    setCorrection(null);

    (async () => {
      try {
        const correctionRequest =
          typeof memoryDashboardApi.listJournal === "function"
            ? memoryDashboardApi
                .listJournal(agentId, {
                  action: "user_edit",
                  target_atom_id: atom.id,
                  limit: 1,
                })
                .catch(() => null)
            : Promise.resolve(null);

        if (
          !atom.candidate_id ||
          typeof memoryDashboardApi.getCandidate !== "function"
        ) {
          const correctionResult = await correctionRequest;
          if (!cancelled) setCorrection(correctionResult?.items[0] ?? null);
          return;
        }
        const cand = (await memoryDashboardApi
          .getCandidate(agentId, atom.candidate_id)
          .catch(() => null)) as CandidateItem | null;
        if (cancelled) return;
        const correctionResult = await correctionRequest;
        if (cancelled) return;
        setCorrection(correctionResult?.items[0] ?? null);
        const eventId = cand?.quote_event_id;
        if (eventId && typeof memoryDashboardApi.getRawEvent === "function") {
          const ev = (await memoryDashboardApi
            .getRawEvent(agentId, eventId)
            .catch(() => null)) as RawEventShape | null;
          if (cancelled) return;
          setRawEvent(ev);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [agentId, atom.id, atom.candidate_id]);

  if (loading) {
    return (
      <div style={lineageBox}>
        <Skeleton active paragraph={{ rows: 1 }} title={false} />
      </div>
    );
  }

  const fromQuote = rawEvent?.content || rawEvent?.text || atom.verbatim_quote;
  const beforeAssertion = correction?.before?.assertion;
  const correctionText =
    typeof beforeAssertion === "string" && beforeAssertion.trim()
      ? beforeAssertion
      : null;
  const sourceLabel = correction
    ? t("memory.lineage.originalContext", "原始来源上下文：")
    : rawEvent?.event_type === "manual"
    ? t("memory.lineage.manualEntry", "人工添加的记忆：")
    : t("memory.lineage.conversationSource", "来源对话片段：");

  return (
    <div>
      {correction ? (
        <div style={correctionBox}>
          <Typography.Text strong style={{ fontSize: 12 }}>
            ✏️ {t("memory.lineage.manualCorrection", "人工修正的记忆")}
          </Typography.Text>
          {correctionText ? (
            <div style={{ marginTop: 4, fontSize: 12, color: "#595959" }}>
              {t("memory.lineage.beforeCorrection", "修正前：{{assertion}}", {
                assertion: correctionText,
              })}
            </div>
          ) : null}
        </div>
      ) : null}
      <div style={lineageBox}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          🧬 {sourceLabel}
        </Typography.Text>
        {fromQuote ? (
          <div
            style={{
              marginTop: 4,
              fontSize: 12,
              color: "#595959",
              background: "#fafafa",
              padding: "6px 8px",
              borderRadius: 4,
              borderLeft: "3px solid #d9d9d9",
              whiteSpace: "pre-wrap",
              maxHeight: 80,
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {truncate(String(fromQuote), 200)}
          </div>
        ) : (
          <div style={{ marginTop: 4, fontSize: 12, color: "#8c8c8c" }}>
            {t("memory.lineage.noOriginalContext", "没有可展示的原始来源")}
          </div>
        )}
      </div>
    </div>
  );
}

const correctionBox: React.CSSProperties = {
  border: "1px solid #91caff",
  background: "#e6f4ff",
  borderRadius: 6,
  padding: "10px 12px",
  marginBottom: 8,
};

const lineageBox: React.CSSProperties = {
  border: "1px solid #f0f0f0",
  background: "#fcfcfc",
  borderRadius: 6,
  padding: "10px 12px",
  marginBottom: 14,
};

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n) + "…";
}
