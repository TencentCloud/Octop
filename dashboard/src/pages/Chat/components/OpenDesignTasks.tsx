import { useState } from "react";
import { Alert, Button, Card, Space, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";
import {
  openDesignApi,
  type DesignTask,
} from "../../../api/modules/openDesign";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import OpenDesignSource from "./OpenDesignSource";
import styles from "./OpenDesignTasks.module.less";

function previewUrl(value: unknown): string | undefined {
  if (typeof value !== "string") return;
  try {
    const url = new URL(value);
    if (["http:", "https:"].includes(url.protocol)) return url.href;
  } catch {
    /* Unavailable preview. */
  }
}

function TaskMessage({ message }: { message: string }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [truncated, setTruncated] = useState(false);
  return (
    <div>
      <Typography.Paragraph
        className={styles.message}
        ellipsis={expanded ? false : { rows: 3, onEllipsis: setTruncated }}
      >
        {message}
      </Typography.Paragraph>
      {(expanded || truncated) && (
        <Button
          type="link"
          size="small"
          className={styles.expand}
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {t(expanded ? "openDesignTasks.collapse" : "openDesignTasks.expand")}
        </Button>
      )}
    </div>
  );
}

export default function OpenDesignTasks({
  agentId,
  threadId,
  tasks,
  onTasks,
}: {
  agentId: string;
  threadId: string;
  tasks: DesignTask[];
  onTasks: (tasks: DesignTask[]) => void;
}) {
  const { t } = useTranslation();
  const timezone = useServerTimezone();
  const [disconnected, setDisconnected] = useState(false);
  const [refreshing, setRefreshing] = useState<string>();
  if (!tasks.length) return null;
  return (
    <section className={styles.tasks} aria-label={t("openDesignTasks.title")}>
      {disconnected && (
        <Alert
          type="warning"
          showIcon
          message={t("openDesignTasks.disconnected")}
        />
      )}
      {tasks.map((task) => {
        const url = previewUrl(task.result.previewUrl);
        return (
          <Card
            key={task.task_id}
            size="small"
            title={`OpenDesign · ${task.project}`}
            extra={
              <Tag
                color={
                  task.status === "succeeded"
                    ? "success"
                    : task.status === "failed"
                    ? "error"
                    : "processing"
                }
              >
                {t(`openDesignTasks.status.${task.status}`, {
                  defaultValue: task.status,
                })}
              </Tag>
            }
          >
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Typography.Text type="secondary">
                {t("openDesignTasks.updated", {
                  time: formatServerDateTime(task.updated_at, timezone),
                })}
              </Typography.Text>
              {task.last_error && (
                <Alert
                  type="warning"
                  showIcon
                  message={t(`openDesignTasks.errors.${task.last_error}`, {
                    defaultValue: task.last_error,
                  })}
                />
              )}
              {task.result.agentMessage && (
                <TaskMessage message={task.result.agentMessage} />
              )}
              <Space wrap>
                <OpenDesignSource
                  agentId={agentId}
                  threadId={threadId}
                  task={task}
                />
                {task.run_id &&
                  ["queued", "running", "unavailable"].includes(
                    task.status,
                  ) && (
                    <Button
                      danger
                      loading={refreshing === task.task_id}
                      onClick={async () => {
                        setRefreshing(task.task_id);
                        try {
                          onTasks(
                            await openDesignApi.cancel(
                              agentId,
                              threadId,
                              task.task_id,
                            ),
                          );
                        } catch {
                          setDisconnected(true);
                        } finally {
                          setRefreshing(undefined);
                        }
                      }}
                    >
                      {t("openDesignTasks.cancel")}
                    </Button>
                  )}
                {url && (
                  <Button
                    type="primary"
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t("openDesignTasks.preview")}
                  </Button>
                )}
                <Button
                  loading={refreshing === task.task_id}
                  onClick={async () => {
                    setRefreshing(task.task_id);
                    try {
                      onTasks(
                        await openDesignApi.refresh(
                          agentId,
                          threadId,
                          task.task_id,
                        ),
                      );
                    } catch {
                      setDisconnected(true);
                    } finally {
                      setRefreshing(undefined);
                    }
                  }}
                >
                  {t("openDesignTasks.refresh")}
                </Button>
              </Space>
            </Space>
          </Card>
        );
      })}
    </section>
  );
}
