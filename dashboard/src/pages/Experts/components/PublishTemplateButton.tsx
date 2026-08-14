import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Dropdown, Modal, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";
import { Upload } from "lucide-react";
import {
  publishedExpertsApi,
  type PublishedExpert,
} from "../../../api/modules/publishedExperts";
import { apiErrorMessage } from "../../../utils/apiError";
import type { OctopAgent } from "../../../context/AgentContext";
import styles from "../index.module.less";

interface PublishTemplateButtonProps {
  agent: OctopAgent;
  published: PublishedExpert | null;
  onChanged: () => void;
  /** Optional class for the icon button (card vs table). */
  buttonClassName?: string;
}

export default function PublishTemplateButton({
  agent,
  published,
  onChanged,
  buttonClassName = styles.agentCard2NameActionBtn,
}: PublishTemplateButtonProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);

  const runPublish = async () => {
    setLoading(true);
    try {
      await publishedExpertsApi.publish(agent.agent_id, {
        name: agent.name,
        description: agent.description || undefined,
      });
      message.success(t("experts.published.publishSuccessHint"));
      onChanged();
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("experts.published.publishFailed"), t),
      );
    } finally {
      setLoading(false);
    }
  };

  const confirmPublish = () => {
    Modal.confirm({
      title: t("experts.published.publishConfirmTitle"),
      content: t("experts.published.publishConfirm"),
      okText: t("experts.published.publish"),
      cancelText: t("common.cancel"),
      onOk: () => runPublish(),
    });
  };

  const runRefresh = async () => {
    if (!published) return;
    setLoading(true);
    try {
      await publishedExpertsApi.refresh(published.id);
      message.success(t("experts.published.updateSuccess"));
      onChanged();
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("experts.published.updateFailed"), t),
      );
    } finally {
      setLoading(false);
    }
  };

  const confirmUnpublish = () => {
    if (!published) return;
    Modal.confirm({
      title: t("experts.published.unpublishConfirm"),
      okText: t("experts.published.unpublish"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        setLoading(true);
        try {
          await publishedExpertsApi.unpublish(published.id);
          message.success(t("experts.published.unpublishSuccess"));
          onChanged();
        } catch (err) {
          message.error(
            apiErrorMessage(err, t("experts.published.unpublishFailed"), t),
          );
        } finally {
          setLoading(false);
        }
      },
    });
  };

  const iconButton = (
    <button
      type="button"
      className={buttonClassName}
      disabled={loading}
      onClick={published ? undefined : confirmPublish}
      aria-label={
        published
          ? t("experts.published.badge")
          : t("experts.published.cardPublish")
      }
    >
      <Upload size={12} />
    </button>
  );

  if (published) {
    return (
      <Dropdown
        menu={{
          items: [
            {
              key: "update",
              label: t("experts.published.update"),
              onClick: () => void runRefresh(),
            },
            {
              key: "unpublish",
              danger: true,
              label: t("experts.published.unpublish"),
              onClick: confirmUnpublish,
            },
          ],
        }}
        trigger={["click"]}
        disabled={loading}
      >
        <Tooltip title={t("experts.published.badge")} mouseEnterDelay={0.5}>
          {iconButton}
        </Tooltip>
      </Dropdown>
    );
  }

  return (
    <Tooltip title={t("experts.published.cardPublish")} mouseEnterDelay={0.5}>
      {iconButton}
    </Tooltip>
  );
}
