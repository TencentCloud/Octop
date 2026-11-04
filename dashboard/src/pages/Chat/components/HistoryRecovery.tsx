import { Alert, Button, Space, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../hooks/sseHelpers";

export default function HistoryRecovery({
  messages,
  onRetry,
  onRestore,
}: {
  messages: ChatMessage[];
  onRetry: () => void;
  onRestore: (message: ChatMessage) => void;
}) {
  const { t } = useTranslation();
  if (!messages.length) return null;
  return (
    <Alert
      type="info"
      showIcon
      message={t("chat.historyRecoveryTitle")}
      action={
        <Button size="small" onClick={onRetry}>
          {t("chat.historyRetry")}
        </Button>
      }
      description={
        <details>
          <summary>{t("chat.historyRecoveryDescription")}</summary>
          <div style={{ maxHeight: 240, overflowY: "auto" }}>
            {messages.map((message) => (
              <div key={message.id}>
                <Typography.Paragraph
                  copyable
                  style={{ whiteSpace: "pre-wrap" }}
                >
                  {message.content ||
                    message.toolData?.output ||
                    message.contentBlocks
                      ?.map((block) => block.content)
                      .join("\n") ||
                    ""}
                </Typography.Paragraph>
                {message.attachments?.map((attachment, index) => (
                  <div key={index}>
                    {attachment.filename || attachment.workspacePath}
                  </div>
                ))}
                {message.role === "user" && (
                  <Space>
                    <Button size="small" onClick={() => onRestore(message)}>
                      {t("chat.historyRecoveryRestore")}
                    </Button>
                  </Space>
                )}
              </div>
            ))}
          </div>
        </details>
      }
    />
  );
}
