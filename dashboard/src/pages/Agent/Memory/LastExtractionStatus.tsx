import { Alert, Typography } from "antd";
import { useTranslation } from "react-i18next";

import type { LastExtractRun } from "../../../api/modules/memoryDashboard";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";

export default function LastExtractionStatus({
  run,
}: {
  run?: LastExtractRun | null;
}) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  if (!run) return null;

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
                {t(
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
