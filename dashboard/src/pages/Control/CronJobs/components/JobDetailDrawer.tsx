import {
  Button,
  Drawer,
  Descriptions,
  Badge,
  Tag,
  Typography,
  Divider,
  Alert,
} from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { MessageSquare } from "lucide-react";
import type { CronJobSpecOutput } from "../../../../api/types";
import { setPendingPrefillText } from "../../../Chat/hooks/chatStore";
import {
  channelFromSessionKey,
  extractPromptFromJob,
  formatCronTimestamp,
} from "../cronDisplay";

const { Text } = Typography;

type CronJob = CronJobSpecOutput;

interface JobDetailDrawerProps {
  open: boolean;
  job: CronJob | null;
  timeZone: string;
  onClose: () => void;
}

export function JobDetailDrawer({
  open,
  job,
  timeZone,
  onClose,
}: JobDetailDrawerProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (!job) return null;

  const meta = (job.meta as Record<string, unknown> | undefined) ?? {};
  const sessionKey =
    typeof meta.octop_session_key === "string" ? meta.octop_session_key : "";
  const channel = sessionKey
    ? channelFromSessionKey(sessionKey)
    : String(job.dispatch?.channel || "—");
  const agentPrompt = extractPromptFromJob(job) || null;
  const lastStatus =
    typeof meta.octop_last_status === "string" ? meta.octop_last_status : "";
  const lastError =
    typeof meta.octop_last_error === "string" && meta.octop_last_error.trim()
      ? meta.octop_last_error
      : null;

  const handleGoToChat = () => {
    onClose();
    setPendingPrefillText(agentPrompt ?? "");
    navigate("/chat", { state: { prefillInput: agentPrompt ?? "" } });
  };

  return (
    <Drawer
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Badge
            status={job.enabled ? "success" : "default"}
            text={
              <span style={{ fontWeight: 600, fontSize: 15 }}>
                {job.name || job.id}
              </span>
            }
          />
        </div>
      }
      open={open}
      onClose={onClose}
      width={480}
      destroyOnClose
      footer={
        agentPrompt ? (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button
              type="primary"
              icon={<MessageSquare size={14} />}
              onClick={handleGoToChat}
            >
              {t("cronJobs.goToChat", "发送到聊天")}
            </Button>
          </div>
        ) : null
      }
    >
      {/* Basic information */}
      <Divider
        orientation="left"
        orientationMargin={0}
        style={{ fontSize: 13, fontWeight: 600, marginTop: 0 }}
      >
        {t("cronJobs.form.sectionBasic")}
      </Divider>
      <Descriptions
        column={1}
        size="small"
        labelStyle={{ color: "var(--fn-text-tertiary)", width: 120 }}
      >
        <Descriptions.Item label={t("cronJobs.col.id")}>
          <Text copyable style={{ fontSize: 12, fontFamily: "monospace" }}>
            {job.id}
          </Text>
        </Descriptions.Item>
        <Descriptions.Item label={t("common.enabled")}>
          {job.enabled ? (
            <Tag color="success">{t("common.enabled")}</Tag>
          ) : (
            <Tag color="default">{t("common.disabled")}</Tag>
          )}
        </Descriptions.Item>
      </Descriptions>

      {/* Schedule settings */}
      <Divider
        orientation="left"
        orientationMargin={0}
        style={{ fontSize: 13, fontWeight: 600 }}
      >
        {t("cronJobs.form.sectionSchedule")}
      </Divider>
      <Descriptions
        column={1}
        size="small"
        labelStyle={{ color: "var(--fn-text-tertiary)", width: 120 }}
      >
        <Descriptions.Item label={t("cronJobs.col.trigger")}>
          <Text code style={{ fontSize: 12 }}>
            {job.schedule?.cron || "—"}
          </Text>
        </Descriptions.Item>
        <Descriptions.Item label={t("cronJobs.form.timezone")}>
          {job.schedule?.timezone || "—"}
        </Descriptions.Item>
        <Descriptions.Item label={t("cronJobs.col.lastRunAt")}>
          {formatCronTimestamp(
            typeof meta.octop_last_run_at === "number"
              ? meta.octop_last_run_at
              : null,
            timeZone,
          )}
        </Descriptions.Item>
        <Descriptions.Item label={t("cronJobs.col.lastStatus")}>
          {lastStatus ? (
            <Tag
              color={
                lastStatus === "error"
                  ? "error"
                  : lastStatus === "ok"
                  ? "success"
                  : "default"
              }
            >
              {lastStatus}
            </Tag>
          ) : (
            "—"
          )}
        </Descriptions.Item>
        {lastError && (
          <Descriptions.Item label={t("cronJobs.col.lastError")}>
            <Alert
              type="error"
              showIcon
              message={
                <Text style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>
                  {lastError}
                </Text>
              }
              style={{ padding: "8px 12px" }}
            />
          </Descriptions.Item>
        )}
      </Descriptions>

      <Divider
        orientation="left"
        orientationMargin={0}
        style={{ fontSize: 13, fontWeight: 600 }}
      >
        {t("cronJobs.form.sectionTask")}
      </Divider>
      <Descriptions
        column={1}
        size="small"
        labelStyle={{ color: "var(--fn-text-tertiary)", width: 120 }}
      >
        <Descriptions.Item label={t("cronJobs.col.taskType")}>
          {job.task_type === "text"
            ? t("cronJobs.form.taskTypeText")
            : t("cronJobs.form.taskTypeAgent")}
        </Descriptions.Item>
        {agentPrompt && (
          <Descriptions.Item label={t("cronJobs.col.prompt")}>
            <Text style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>
              {agentPrompt}
            </Text>
          </Descriptions.Item>
        )}
        {job.model || meta.octop_model ? (
          <Descriptions.Item label={t("cronJobs.form.model")}>
            {String(job.model || meta.octop_model)}
          </Descriptions.Item>
        ) : null}
        <Descriptions.Item label={t("cronJobs.col.freshThread")}>
          {meta.octop_fresh_thread
            ? t("cronJobs.col.freshThreadOn")
            : t("cronJobs.col.freshThreadOff")}
        </Descriptions.Item>
      </Descriptions>

      <Divider
        orientation="left"
        orientationMargin={0}
        style={{ fontSize: 13, fontWeight: 600 }}
      >
        {t("cronJobs.form.sectionRouting")}
      </Divider>
      <Descriptions
        column={1}
        size="small"
        labelStyle={{ color: "var(--fn-text-tertiary)", width: 120 }}
      >
        <Descriptions.Item label={t("cronJobs.col.dispatchChannel")}>
          {channel}
        </Descriptions.Item>
        {sessionKey && (
          <Descriptions.Item label={t("cronJobs.col.sessionKey")}>
            <Text copyable style={{ fontSize: 12, fontFamily: "monospace" }}>
              {sessionKey}
            </Text>
          </Descriptions.Item>
        )}
      </Descriptions>
    </Drawer>
  );
}
