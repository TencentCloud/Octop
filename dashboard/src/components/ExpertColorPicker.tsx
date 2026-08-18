import { ColorPicker, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import type { AggregationColor } from "antd/es/color-picker/color";
import {
  DEFAULT_CUSTOM_COLOR,
  PALETTE_SWATCH,
  VALID_PALETTES,
  type ThemePalette,
} from "../styles/themePalettes";
import styles from "./PaletteSwitcher.module.less";

interface ExpertColorPickerProps {
  /** Curated palette key, or an arbitrary hex string for a custom color. */
  value: string;
  onChange: (value: string) => void;
}

function isCurated(value: string): value is ThemePalette {
  return (VALID_PALETTES as string[]).includes(value);
}

/**
 * Curated 8-swatch picker for expert/agent accent color, plus a custom
 * color swatch backed by the Ant Design color picker (palette + hex input).
 * The onChange callback receives a palette key or a hex string.
 */
export default function ExpertColorPicker({
  value,
  onChange,
}: ExpertColorPickerProps) {
  const { t } = useTranslation();
  const curated = isCurated(value);

  return (
    <div className={styles.picker} role="group" aria-label={t("experts.color")}>
      {VALID_PALETTES.map((key) => {
        const active = value === key;
        const label = t(`header.palette.${key}`);
        return (
          <Tooltip key={key} title={label} mouseEnterDelay={0.35}>
            <button
              type="button"
              className={`${styles.option} ${active ? styles.active : ""}`}
              aria-label={label}
              aria-pressed={active}
              onClick={() => onChange(key)}
            >
              <span
                className={styles.swatch}
                style={{ backgroundColor: PALETTE_SWATCH[key] }}
                aria-hidden
              />
            </button>
          </Tooltip>
        );
      })}
      <Tooltip title={t("experts.customColor")} mouseEnterDelay={0.35}>
        <span
          className={`${styles.option} ${!curated ? styles.active : ""}`}
          aria-label={t("experts.customColor")}
          aria-pressed={!curated}
          role="button"
        >
          <ColorPicker
            value={curated ? undefined : value}
            onChangeComplete={(color: AggregationColor) => {
              onChange(color.toHexString());
            }}
            disabledAlpha
          >
            <span
              className={`${styles.swatch} ${styles.customSwatch}`}
              style={!curated ? { backgroundColor: value } : undefined}
              aria-hidden
            />
          </ColorPicker>
        </span>
      </Tooltip>
      {!curated && value !== DEFAULT_CUSTOM_COLOR && (
        <span className={styles.customHex}>{value.toUpperCase()}</span>
      )}
    </div>
  );
}
