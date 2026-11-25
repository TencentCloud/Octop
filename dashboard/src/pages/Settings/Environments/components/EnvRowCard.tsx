import { useState } from "react";
import { Checkbox, Input } from "antd";
import { Plus, Trash2, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import { isSensitiveKey } from "../utils";
import type { Row } from "./EnvRow";
import styles from "../index.module.less";

interface EnvRowCardProps {
  row: Row;
  idx: number;
  checked: boolean;
  error?: string;
  onToggle: (idx: number) => void;
  onChange: (idx: number, field: "key" | "value", val: string) => void;
  onInsert: (idx: number) => void;
  onRemove: (idx: number) => void;
}

/** Mobile-friendly card layout for one environment variable row. */
export function EnvRowCard({
  row,
  idx,
  checked,
  error,
  onToggle,
  onChange,
  onInsert,
  onRemove,
}: EnvRowCardProps) {
  const { t } = useTranslation();
  const [isValueVisible, setIsValueVisible] = useState(false);
  const isSensitive = isSensitiveKey(row.key);

  return (
    <div
      className={cx(styles.envRowCard, checked && styles.envRowCardSelected)}
    >
      <div className={styles.envRowCardHeader}>
        <Checkbox checked={checked} onChange={() => onToggle(idx)} />
        <div className={styles.envRowCardActions}>
          <button
            type="button"
            className={styles.rowIconBtn}
            onClick={() => onInsert(idx)}
            title={t("environments.insertRowBelow")}
            aria-label={t("environments.insertRowBelow")}
          >
            <Plus size={16} />
          </button>
          <button
            type="button"
            className={cx(styles.rowIconBtn, styles.rowIconBtnDanger)}
            onClick={() => onRemove(idx)}
            title={t("environments.deleteRow")}
            aria-label={t("environments.deleteRow")}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div className={styles.envRowCardField}>
        <label className={styles.envRowCardLabel}>Key</label>
        <Input
          value={row.key}
          placeholder="Variable Name"
          disabled={!row.isNew}
          onChange={(e) => onChange(idx, "key", e.target.value)}
          status={error ? "error" : undefined}
          autoFocus={row.isNew}
        />
      </div>

      <div className={styles.envRowCardField}>
        <label className={styles.envRowCardLabel}>Value</label>
        <div className={styles.envRowCardValueWrap}>
          <Input
            value={row.value}
            placeholder="Value"
            onChange={(e) => onChange(idx, "value", e.target.value)}
            type={isSensitive && !isValueVisible ? "password" : "text"}
          />
          {isSensitive && (
            <button
              type="button"
              className={styles.envRowCardValueToggle}
              onClick={() => setIsValueVisible(!isValueVisible)}
              title={
                isValueVisible
                  ? t("environments.hideValue")
                  : t("environments.showValue")
              }
              aria-label={
                isValueVisible
                  ? t("environments.hideValue")
                  : t("environments.showValue")
              }
            >
              {isValueVisible ? <Eye size={16} /> : <EyeOff size={16} />}
            </button>
          )}
        </div>
      </div>

      {error && <div className={styles.rowError}>{error}</div>}
    </div>
  );
}
