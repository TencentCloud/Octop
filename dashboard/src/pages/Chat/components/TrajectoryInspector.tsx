import { Tabs } from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  trajectoryApi,
  type TrajectoryEvent,
} from "../../../api/modules/trajectory";
import Markdown from "../../../components/Markdown/LazyMarkdown";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { splitMarkdownFrontmatter } from "../../../utils/markdown";
import {
  kindLabelFor,
  formatDurationMs,
  coerceToolResultText,
  coerceToolArgsText,
} from "../utils/trajectoryModel";
import styles from "./TrajectoryInspector.module.less";

export interface TrajectoryInspectorProps {
  agentId: string;
  threadId: string;
  event: TrajectoryEvent | null;
  /** All loaded events — used to resolve Source → Request # jumps. */
  events?: TrajectoryEvent[];
  onSelectEvent?: (eventId: string) => void;
}

function payloadNumber(
  payload: Record<string, unknown>,
  key: string,
): number | null {
  const value = payload[key];
  return typeof value === "number" ? value : null;
}

/** Prefer the assistant row for a request; fall back to any matching event. */
export function findSourceEventId(
  events: readonly TrajectoryEvent[],
  requestSeq: number,
  currentEventId?: string,
): string | null {
  let fallback: string | null = null;
  for (const event of events) {
    if (event.request_seq !== requestSeq) continue;
    if (event.event_id === currentEventId) continue;
    if (event.kind === "assistant") return event.event_id;
    if (fallback == null) fallback = event.event_id;
  }
  return fallback;
}

function formatStartedAt(ts: number, timeZone?: string): string {
  // Trajectory timestamps are unix seconds (float); tolerate ms.
  if (!Number.isFinite(ts) || ts <= 0) return "—";
  const epochSec = ts > 1e12 ? ts / 1000 : ts;
  return formatServerDateTime(epochSec, timeZone);
}

function TimingSection({ event }: { event: TrajectoryEvent }) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const total =
    payloadNumber(event.payload, "llm_duration_ms") ??
    payloadNumber(event.payload, "tool_duration_ms");
  const ttft = payloadNumber(event.payload, "ttft_ms");
  const tokPerS = payloadNumber(event.payload, "tok_per_s");
  const generation =
    total != null && ttft != null && total >= ttft ? total - ttft : null;

  const hasTiming =
    total != null || ttft != null || tokPerS != null || event.ts > 0;
  if (!hasTiming) return null;

  return (
    <details className={styles.section} open>
      <summary className={styles.sectionSummary}>
        {t("chat.trajectoryInspectorTiming", "Request Timing")}
      </summary>
      <dl className={styles.summary}>
        <div className={styles.field}>
          <dt>{t("chat.trajectoryInspectorStarted", "Started")}</dt>
          <dd>{formatStartedAt(event.ts, timeZone)}</dd>
        </div>
        {total != null ? (
          <div className={styles.field}>
            <dt>
              {t("chat.trajectoryInspectorTotalDuration", "Total duration")}
            </dt>
            <dd>{formatDurationMs(total)}</dd>
          </div>
        ) : null}
        {ttft != null ? (
          <div className={styles.field}>
            <dt>{t("chat.trajectoryInspectorTtft", "TTFT")}</dt>
            <dd>{formatDurationMs(ttft)}</dd>
          </div>
        ) : null}
        {generation != null ? (
          <div className={styles.field}>
            <dt>{t("chat.trajectoryInspectorGeneration", "Generation")}</dt>
            <dd>{formatDurationMs(generation)}</dd>
          </div>
        ) : null}
        {tokPerS != null ? (
          <div className={styles.field}>
            <dt>{t("chat.trajectoryInspectorThroughput", "Throughput")}</dt>
            <dd>{`${
              Number.isInteger(tokPerS) ? tokPerS : tokPerS.toFixed(1)
            } tok/s`}</dd>
          </div>
        ) : null}
      </dl>
    </details>
  );
}

function SummaryPane({
  event,
  events,
  onSelectEvent,
}: {
  event: TrajectoryEvent;
  events: TrajectoryEvent[];
  onSelectEvent?: (eventId: string) => void;
}) {
  const { t } = useTranslation();
  const inputTokens = payloadNumber(event.payload, "input_tokens");
  const outputTokens = payloadNumber(event.payload, "output_tokens");
  const sourceId =
    event.request_seq != null
      ? findSourceEventId(events, event.request_seq, event.event_id)
      : null;
  const canJump =
    sourceId != null &&
    onSelectEvent != null &&
    // Jumping from a tool (or other) to its assistant; or from assistant to
    // another event in the same request is useful. Skip self-only dead ends.
    sourceId !== event.event_id;

  return (
    <div className={styles.summaryScroll}>
      <dl className={styles.summary}>
        <div className={styles.field}>
          <dt>{t("chat.trajectoryInspectorKind", "Kind")}</dt>
          <dd>{kindLabelFor(event.kind)}</dd>
        </div>
        {event.request_seq != null ? (
          <div className={styles.field}>
            <dt>{t("chat.trajectoryInspectorSource", "Source")}</dt>
            <dd>
              {canJump ? (
                <button
                  type="button"
                  className={styles.sourceJump}
                  data-testid="trajectory-source-jump"
                  onClick={() => onSelectEvent(sourceId)}
                >
                  {`Request #${event.request_seq}`}
                  <span className={styles.sourceChevron} aria-hidden>
                    ›
                  </span>
                </button>
              ) : (
                `Request #${event.request_seq}`
              )}
            </dd>
          </div>
        ) : null}
        <div className={styles.field}>
          <dt>{t("chat.trajectoryInspectorStatus", "Status")}</dt>
          <dd>
            {event.is_error
              ? t("chat.trajectoryInspectorError", "Error")
              : t("chat.trajectoryInspectorCompleted", "Completed")}
          </dd>
        </div>
        {inputTokens != null || outputTokens != null ? (
          <div className={styles.field}>
            <dt>{t("chat.trajectoryInspectorTokens", "Tokens")}</dt>
            <dd>
              {[inputTokens, outputTokens]
                .filter((value): value is number => value != null)
                .map((value) => `${value} tok`)
                .join(" · ")}
            </dd>
          </div>
        ) : null}
      </dl>
      <TimingSection event={event} />
    </div>
  );
}

function RawPane({
  agentId,
  threadId,
  eventId,
}: {
  agentId: string;
  threadId: string;
  eventId: string;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    void trajectoryApi
      .event(agentId, threadId, eventId)
      .then((detail) => {
        if (!cancelled) {
          setText(JSON.stringify(detail.payload, null, 2));
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, eventId, threadId]);

  return (
    <pre className={styles.raw} data-testid="trajectory-raw">
      {loading
        ? t("chat.trajectoryDetailLoading", "Loading detail…")
        : failed
        ? t("chat.trajectoryDetailError", "Failed to load event detail")
        : text}
    </pre>
  );
}

function previewTextFromDetail(
  detail: TrajectoryEvent,
  fallback: string,
): string {
  const payload = detail.payload ?? {};
  if (detail.kind === "tool") {
    return (
      coerceToolResultText(payload.result) ??
      coerceToolResultText(payload.output) ??
      coerceToolResultText(payload.content) ??
      (detail.summary || fallback)
    );
  }
  const content = payload.content;
  if (typeof content === "string" && content.trim()) return content;
  const text = payload.text;
  if (typeof text === "string" && text.trim()) return text;
  const result = coerceToolResultText(payload.result);
  if (result) return result;
  return detail.summary || fallback;
}

function PayloadPane({ event }: { event: TrajectoryEvent }) {
  const { t } = useTranslation();
  const args =
    event.payload.args ?? event.payload.arguments ?? event.payload.input;
  const text = coerceToolArgsText(args);
  return (
    <div className={styles.previewPlain} data-testid="trajectory-payload">
      {text || t("chat.trajectoryInspectorEmptyPayload", "No payload")}
    </div>
  );
}

function PreviewPane({
  agentId,
  threadId,
  event,
}: {
  agentId: string;
  threadId: string;
  event: TrajectoryEvent;
}) {
  const { t } = useTranslation();
  const plain = event.kind === "tool";
  const initial = plain
    ? coerceToolResultText(event.payload.result) ||
      coerceToolResultText(event.payload.output) ||
      event.summary ||
      ""
    : event.summary || "";
  const [text, setText] = useState(initial);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fallback =
      (plain
        ? coerceToolResultText(event.payload.result) ||
          coerceToolResultText(event.payload.output)
        : null) ||
      event.summary ||
      "";
    setLoading(true);
    setText(fallback);
    void trajectoryApi
      .event(agentId, threadId, event.event_id)
      .then((detail) => {
        if (!cancelled) {
          setText(previewTextFromDetail(detail, fallback));
        }
      })
      .catch(() => {
        /* keep summary fallback */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    agentId,
    event.event_id,
    event.kind,
    event.payload.result,
    event.payload.output,
    event.summary,
    plain,
    threadId,
  ]);

  return (
    <div
      className={plain ? styles.previewPlain : styles.preview}
      data-testid="trajectory-preview"
    >
      {loading && !text ? (
        t("chat.trajectoryDetailLoading", "Loading detail…")
      ) : text ? (
        plain ? (
          text
        ) : (
          <Markdown content={splitMarkdownFrontmatter(text).body || text} />
        )
      ) : null}
    </div>
  );
}

export default function TrajectoryInspector({
  agentId,
  threadId,
  event,
  events = [],
  onSelectEvent,
}: TrajectoryInspectorProps) {
  const { t } = useTranslation();

  if (event == null) {
    return (
      <div className={styles.placeholder}>
        {t("chat.trajectoryInspectorPlaceholder", "Select a record")}
      </div>
    );
  }

  const kindLabel = kindLabelFor(event.kind);
  const locationParts = [
    event.request_seq != null ? `Request #${event.request_seq}` : null,
    `Step ${event.seq}`,
  ].filter(Boolean);

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <span className={styles.headerKind} data-kind={event.kind}>
            {kindLabel}
          </span>
          {locationParts.length > 0 ? (
            <span className={styles.headerLocation}>
              {locationParts.join(" · ")}
            </span>
          ) : null}
        </div>
      </header>
      <Tabs
        destroyOnHidden
        className={styles.tabs}
        items={[
          {
            key: "summary",
            label: t("chat.trajectoryInspectorSummary", "Summary"),
            children: (
              <SummaryPane
                event={event}
                events={events}
                onSelectEvent={onSelectEvent}
              />
            ),
          },
          ...(event.kind === "tool"
            ? [
                {
                  key: "payload",
                  label: t("chat.trajectoryInspectorPayload", "Payload"),
                  children: <PayloadPane event={event} />,
                },
              ]
            : []),
          {
            key: "preview",
            label:
              event.kind === "tool"
                ? t("chat.trajectoryInspectorResult", "Result")
                : t("chat.trajectoryInspectorPreview", "Preview"),
            children: (
              <PreviewPane
                agentId={agentId}
                threadId={threadId}
                event={event}
              />
            ),
          },
          {
            key: "raw",
            label: t("chat.trajectoryInspectorRaw", "Raw"),
            children: (
              <RawPane
                agentId={agentId}
                threadId={threadId}
                eventId={event.event_id}
              />
            ),
          },
        ]}
      />
    </div>
  );
}
