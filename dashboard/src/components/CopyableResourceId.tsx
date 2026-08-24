import { useCallback } from "react";
import { Tooltip } from "antd";
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { message } from "@/utils/antdMessage";
import { copyText } from "@/utils/copyText";
import styles from "./CopyableResourceId.module.less";

type CopyableResourceIdProps = {
  label: string;
  value: string;
  copyTitle?: string;
  className?: string;
  /** Match surrounding meta text (e.g. creator line). */
  inline?: boolean;
};

export function CopyableResourceId({
  label,
  value,
  copyTitle,
  className,
  inline = false,
}: CopyableResourceIdProps) {
  const { t } = useTranslation();

  const copy = useCallback(async () => {
    const ok = await copyText(value);
    if (ok) message.success(t("common.copied"));
    else message.error(t("common.copyFailed"));
  }, [t, value]);

  return (
    <Tooltip title={copyTitle ?? t("common.copy")}>
      <button
        type="button"
        className={`${inline ? styles.inlineRoot : styles.root}${
          className ? ` ${className}` : ""
        }`}
        onClick={() => void copy()}
      >
        <span className={inline ? styles.inlineText : styles.label}>
          {inline ? `${label}: ${value}` : label}
        </span>
        {!inline ? <span className={styles.value}>{value}</span> : null}
        <Copy
          size={inline ? 12 : 11}
          className={inline ? styles.inlineIcon : styles.icon}
          aria-hidden
        />
      </button>
    </Tooltip>
  );
}
