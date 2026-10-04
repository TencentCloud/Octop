import { Alert, Button } from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { OctopEmptyMascot } from "../../../components/EmptyState";
import styles from "../index.module.less";

interface ModelConfigEmptyProps {
  canConfigure: boolean;
  compact?: boolean;
}

export default function ModelConfigEmpty({
  canConfigure,
  compact = false,
}: ModelConfigEmptyProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (compact)
    return (
      <Alert
        className="wb-readiness-notice"
        showIcon
        type="info"
        message={t("modelConfig.promptTitle")}
        description={t(
          canConfigure
            ? "modelConfig.promptMessage"
            : "modelConfig.promptMessageNoPermission",
        )}
        action={
          canConfigure ? (
            <Button onClick={() => navigate("/admin/models")}>
              {t("modelConfig.configureButton")}
            </Button>
          ) : undefined
        }
      />
    );

  return (
    <div className={styles.noAgentsEmpty}>
      <div className={styles.noAgentsEmptyInner}>
        <div className={styles.noAgentsEmptyIcon}>
          <OctopEmptyMascot className={styles.noAgentsEmptyMascot} />
        </div>
        <h1 className={styles.noAgentsEmptyTitle}>
          {t("modelConfig.promptTitle")}
        </h1>
        <p className={styles.noAgentsEmptyHint}>
          {canConfigure
            ? t("modelConfig.promptMessage")
            : t("modelConfig.promptMessageNoPermission")}
        </p>
        {canConfigure ? (
          <Button
            type="primary"
            size="large"
            onClick={() => navigate("/admin/models")}
          >
            {t("modelConfig.configureButton")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
