import type { AriaAttributes, ReactNode } from "react";
import { Button, Drawer, Space } from "antd";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "./expertDrawer.module.less";

interface ExpertConfigDrawerProps extends AriaAttributes {
  id?: string;
  title: string;
  summary: string;
  open: boolean;
  disabled?: boolean;
  applyDisabled?: boolean;
  onOpen: () => void;
  onClose: () => void;
  onApply?: () => void;
  formId?: string;
  children: ReactNode;
}

export default function ExpertConfigDrawer({
  id,
  title,
  summary,
  open,
  disabled,
  applyDisabled,
  onOpen,
  onClose,
  onApply,
  formId,
  children,
  ...aria
}: ExpertConfigDrawerProps) {
  const { t } = useTranslation();

  return (
    <>
      <button
        {...aria}
        id={id}
        type="button"
        className={styles.configEntry}
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={onOpen}
      >
        <span className={styles.configEntryText}>
          <span className={styles.configEntryTitle}>{title}</span>
          <span className={styles.configSummary}>{summary}</span>
        </span>
        <ChevronRight size={16} aria-hidden />
      </button>
      <Drawer
        title={title}
        open={open}
        onClose={onClose}
        width="min(520px, 100vw)"
        className={styles.expertDrawer}
        destroyOnHidden
        footer={
          <Space style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <Button
              type="primary"
              htmlType={formId ? "submit" : "button"}
              form={formId}
              onClick={onApply}
              disabled={applyDisabled}
            >
              {t("experts.configDone")}
            </Button>
          </Space>
        }
      >
        <div className={styles.configBody}>{children}</div>
      </Drawer>
    </>
  );
}
