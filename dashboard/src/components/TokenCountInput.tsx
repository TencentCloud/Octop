/**
 * Numeric token input with quick presets and a human-readable K/M preview.
 * Stores absolute token counts; presets/preview prefer K (or M when ≥1M).
 */
import { InputNumber } from "antd";
import { useTranslation } from "react-i18next";
import styles from "./TokenCountInput.module.less";

export function formatTokenScaleLabel(tokens: number): string {
  if (tokens >= 1_000_000) {
    const millions = tokens / 1_000_000;
    return `${trimScale(millions)}M`;
  }
  if (tokens >= 1_000) {
    const kilos = tokens / 1_000;
    return `${trimScale(kilos)}K`;
  }
  return String(tokens);
}

function trimScale(n: number): string {
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2).replace(/\.?0+$/, "");
}

function formatExact(tokens: number): string {
  return tokens.toLocaleString("en-US");
}

export interface TokenCountInputProps {
  value?: number | null;
  onChange?: (value: number | null) => void;
  placeholder?: string;
  /** Absolute token counts shown as quick-fill chips. */
  presets?: readonly number[];
  min?: number;
  step?: number;
  disabled?: boolean;
}

export function TokenCountInput({
  value,
  onChange,
  placeholder,
  presets = [],
  min = 0,
  step = 1_000,
  disabled,
}: TokenCountInputProps) {
  const { t } = useTranslation();
  const numeric =
    typeof value === "number" && Number.isFinite(value) ? value : null;

  return (
    <div className={styles.field}>
      <InputNumber
        value={numeric ?? undefined}
        onChange={(next) => onChange?.(typeof next === "number" ? next : null)}
        min={min}
        step={step}
        disabled={disabled}
        style={{ width: "100%" }}
        placeholder={placeholder}
        formatter={(raw) =>
          `${raw ?? ""}`.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
        }
        parser={(raw) => {
          const cleaned = (raw ?? "").replace(/,/g, "");
          if (!cleaned) return undefined as unknown as number;
          return Number(cleaned);
        }}
      />
      {presets.length > 0 ? (
        <div className={styles.presets} role="group">
          <span className={styles.presetsLabel}>
            {t("common.tokenCountPresets")}
          </span>
          {presets.map((preset) => {
            const selected = numeric === preset;
            return (
              <button
                key={preset}
                type="button"
                disabled={disabled}
                className={`${styles.preset} ${
                  selected ? styles.presetActive : ""
                }`}
                onClick={() => onChange?.(preset)}
              >
                {formatTokenScaleLabel(preset)}
              </button>
            );
          })}
        </div>
      ) : null}
      {numeric != null && numeric > 0 ? (
        <div className={styles.preview}>
          {t("common.tokenCountPreview", {
            label: formatTokenScaleLabel(numeric),
            exact: formatExact(numeric),
          })}
        </div>
      ) : null}
    </div>
  );
}
