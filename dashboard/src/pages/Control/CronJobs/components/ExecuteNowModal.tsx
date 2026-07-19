import { Modal, Button } from "antd";
import { useTranslation } from "react-i18next";
import type { CronJobSpecOutput } from "../../../../api/types";
import styles from "../index.module.less";

interface ExecuteNowModalProps {
  open: boolean;
  job: CronJobSpecOutput | null;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Polished confirm dialog for the "run task now" action. */
export function ExecuteNowModal({
  open,
  job,
  loading = false,
  onCancel,
  onConfirm,
}: ExecuteNowModalProps) {
  const { t } = useTranslation();

  return (
    <Modal
      open={open}
      onCancel={onCancel}
      footer={null}
      centered
      width={400}
      closable={false}
      maskClosable
      className={styles.executeModal}
    >
      <div className={styles.executeModalBody}>
        <p className={styles.executeModalDesc}>
          {t("cronJobs.executeNowConfirmContent")}
        </p>
        {job?.name ? (
          <div className={styles.executeModalHighlight}>{job.name}</div>
        ) : null}
      </div>
      <div className={styles.executeModalActions}>
        <Button
          onClick={onCancel}
          disabled={loading}
          className={styles.executeModalCancel}
        >
          {t("common.cancel")}
        </Button>
        <Button
          type="primary"
          loading={loading}
          onClick={onConfirm}
          className={styles.executeModalOk}
        >
          {t("cronJobs.executeNowConfirmOk")}
        </Button>
      </div>
    </Modal>
  );
}
