import { Alert, Typography } from "antd";
import { useTranslation } from "react-i18next";

import type {
  CodexReviewRun,
  LastExtractRun,
} from "../../../api/modules/memoryDashboard";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";

function ServerExtraction({ run }: { run: LastExtractRun }) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();

  const reason = run.failure_reason?.trim();
  const timedOut = /timeout|timed[\s_-]*out|超时/i.test(reason ?? "");
  const message = reason
    ? timedOut
      ? t("memory.pipeline.extractTimeout", "最近提取超时，已降级")
      : t("memory.pipeline.extractDegraded", "最近提取未完成，已降级")
    : run.quiet
    ? t("memory.pipeline.extractQuiet", "最近提取完成，无新增记忆")
    : t("memory.pipeline.extractSuccess", "最近提取成功");

  return (
    <Alert
      style={{ marginBottom: 16 }}
      showIcon
      type={reason ? "warning" : run.quiet ? "info" : "success"}
      message={message}
      description={
        <>
          {run.timestamp && (
            <Typography.Text type="secondary">
              {formatServerIsoDateTime(run.timestamp, timeZone)}
            </Typography.Text>
          )}
          {reason && (
            <>
              <p>
                {/no LLM backend configured/i.test(reason)
                  ? t(
                      "memory.pipeline.missingServerModel",
                      "此记录来自服务端提取。如需启用服务端提取，请为 Memory 服务配置模型。",
                    )
                  : t(
                      "memory.pipeline.extractFailureHint",
                      "已有记忆仍可使用。可在记忆设置中调整提取模型、输出预算和请求超时。",
                    )}
              </p>
              <details>
                <summary>
                  {t("memory.pipeline.extractFailureDetails", "失败详情")}
                </summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    overflowWrap: "anywhere",
                    marginBottom: 0,
                  }}
                >
                  {reason}
                </pre>
              </details>
            </>
          )}
        </>
      }
    />
  );
}

export default function LastExtractionStatus({
  run,
  codex,
}: {
  run?: LastExtractRun | null;
  codex?: CodexReviewRun | null;
}) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  if (!codex) return run ? <ServerExtraction run={run} /> : null;

  const review = (
    <Alert
      style={{ marginBottom: 16 }}
      showIcon
      type={codex.status === "proposed" ? "success" : "info"}
      message={t("memory.pipeline.codexReview", "最近 Codex 复核")}
      description={
        <>
          <div>
            {codex.status === "proposed"
              ? t("memory.pipeline.codexProposed", "已提交 {{count}} 条候选", {
                  count: codex.proposals,
                })
              : codex.status === "finished_without_proposal"
              ? t("memory.pipeline.codexFinished", "复核续轮已结束，未收到候选")
              : t(
                  "memory.pipeline.codexCaptured",
                  "原文已上报，尚无复核结果记录",
                )}
          </div>
          <Typography.Text type="secondary">
            {t("memory.pipeline.codexEvidenceTime", "本轮原文时间 {{time}}", {
              time: formatServerIsoDateTime(codex.timestamp, timeZone),
            })}
            {codex.model && ` · ${codex.model}`}
          </Typography.Text>
        </>
      }
    />
  );
  if (!run) return review;
  const serverLabel = t("memory.pipeline.serverExtraction", "上一次服务端提取");
  if (
    run.timestamp &&
    Date.parse(codex.timestamp) > Date.parse(run.timestamp)
  ) {
    return (
      <>
        {review}
        <details style={{ marginBottom: 16 }}>
          <summary>
            {serverLabel} · {formatServerIsoDateTime(run.timestamp, timeZone)}
          </summary>
          <ServerExtraction run={run} />
        </details>
      </>
    );
  }
  return (
    <>
      <Typography.Text>{serverLabel}</Typography.Text>
      <ServerExtraction run={run} />
      {review}
    </>
  );
}
