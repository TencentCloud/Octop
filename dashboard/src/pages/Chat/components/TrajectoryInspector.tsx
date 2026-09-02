import { Tabs } from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  trajectoryApi,
  type TrajectoryEvent,
} from "../../../api/modules/trajectory";
import styles from "./TrajectoryInspector.module.less";

export interface TrajectoryInspectorProps {
  agentId: string;
  threadId: string;
  event: TrajectoryEvent | null;
}

function payloadNumber(
  payload: Record<string, unknown>,
  key: string,
): number | null {
  const value = payload[key];
  return typeof value === "number" ? value : null;
}

function SummaryPane({ event }: { event: TrajectoryEvent }) {
  const { t } = useTranslation();
  const duration =
    payloadNumber(event.payload, "llm_duration_ms") ??
    payloadNumber(event.payload, "tool_duration_ms");
  const ttft = payloadNumber(event.payload, "ttft_ms");
  const inputTokens = payloadNumber(event.payload, "input_tokens");
  const outputTokens = payloadNumber(event.payload, "output_tokens");

  return (
    <dl className={styles.summary}>
      <div className={styles.field}>
        <dt>{t("chat.trajectoryInspectorKind", "Kind")}</dt>
        <dd>{event.kind}</dd>
      </div>
      {event.request_seq != null ? (
        <div className={styles.field}>
          <dt>{t("chat.trajectoryInspectorRequest", "Request")}</dt>
          <dd>{`Request #${event.request_seq}`}</dd>
        </div>
      ) : null}
      <div className={styles.field}>
        <dt>{t("chat.trajectoryInspectorStatus", "Status")}</dt>
        <dd>
          {event.is_error
            ? t("chat.trajectoryInspectorError", "Error")
            : t("chat.trajectoryInspectorOk", "OK")}
        </dd>
      </div>
      {duration != null ? (
        <div className={styles.field}>
          <dt>{t("chat.trajectoryInspectorDuration", "Duration")}</dt>
          <dd>{duration}</dd>
        </div>
      ) : null}
      {ttft != null ? (
        <div className={styles.field}>
          <dt>{t("chat.trajectoryInspectorTtft", "TTFT")}</dt>
          <dd>{ttft}</dd>
        </div>
      ) : null}
      {inputTokens != null || outputTokens != null ? (
        <div className={styles.field}>
          <dt>{t("chat.trajectoryInspectorTokens", "Tokens")}</dt>
          <dd>
            {[inputTokens, outputTokens]
              .filter((value): value is number => value != null)
              .join(" / ")}
          </dd>
        </div>
      ) : null}
    </dl>
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
        ? t("chat.dockTrajectoryDetailLoading", "Loading detail…")
        : failed
        ? t("chat.dockTrajectoryDetailError", "Failed to load event detail")
        : text}
    </pre>
  );
}

export default function TrajectoryInspector({
  agentId,
  threadId,
  event,
}: TrajectoryInspectorProps) {
  const { t } = useTranslation();

  if (event == null) {
    return (
      <div className={styles.placeholder}>
        {t("chat.trajectoryInspectorPlaceholder", "Select a record")}
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <Tabs
        destroyOnHidden
        items={[
          {
            key: "summary",
            label: t("chat.trajectoryInspectorSummary", "Summary"),
            children: <SummaryPane event={event} />,
          },
          {
            key: "preview",
            label: t("chat.trajectoryInspectorPreview", "Preview"),
            children: (
              <pre className={styles.preview}>{event.summary || ""}</pre>
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
