import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Dropdown, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";
import { modal } from "@/utils/antdModal";
import { Upload } from "lucide-react";
import {
  publishedExpertsApi,
  type PublishedExpert,
} from "../../../api/modules/publishedExperts";
import { apiErrorMessage } from "../../../utils/apiError";
import type { OctopAgent } from "../../../context/AgentContext";
import PublishExpertDrawer from "./PublishExpertDrawer";
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
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMode, setDrawerMode] = useState<"publish" | "refresh">(
    "publish",
  );

  const openPublishDrawer = () => {
    setDrawerMode("publish");
    setDrawerOpen(true);
  };

  const openRefreshDrawer = () => {
    setDrawerMode("refresh");
    setDrawerOpen(true);
  };

  const confirmUnpublish = () => {
    if (!published) return;
    modal.confirm({
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
      onClick={published ? undefined : openPublishDrawer}
      aria-label={
        published
          ? t("experts.published.badge")
          : t("experts.published.cardPublish")
      }
    >
      <Upload size={12} />
    </button>
  );

  return (
    <>
      {published ? (
        <Dropdown
          menu={{
            items: [
              {
                key: "update",
                label: t("experts.published.update"),
                onClick: openRefreshDrawer,
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
      ) : (
        <Tooltip
          title={t("experts.published.cardPublish")}
          mouseEnterDelay={0.5}
        >
          {iconButton}
        </Tooltip>
      )}

      <PublishExpertDrawer
        open={drawerOpen}
        mode={drawerMode}
        agent={agent}
        published={published}
        onClose={() => setDrawerOpen(false)}
        onSuccess={onChanged}
      />
    </>
  );
}
