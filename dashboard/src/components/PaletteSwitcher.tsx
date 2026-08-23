import { ColorPicker, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import type { AggregationColor } from "antd/es/color-picker/color";
import { useTheme } from "../context/ThemeContext";
import { PALETTE_SWATCH, VALID_PALETTES } from "../styles/themePalettes";
import styles from "./PaletteSwitcher.module.less";

/**
 * Curated 8-swatch brand palette picker plus a custom color swatch.
 * The custom swatch opens the Ant Design color picker (palette + hex input);
 * picking a color switches the active brand palette to "custom".
 */
export default function PaletteSwitcher() {
  const { palette, setPalette, customColor, setCustomColor } = useTheme();
  const { t } = useTranslation();

  const isCustom = palette === "custom";

  return (
    <div
      className={styles.picker}
      role="group"
      aria-label={t("account.palette")}
    >
      {VALID_PALETTES.map((key) => {
        const active = palette === key;
        const label = t(`header.palette.${key}`);
        return (
          <Tooltip key={key} title={label} mouseEnterDelay={0.35}>
            <button
              type="button"
              className={`${styles.option} ${active ? styles.active : ""}`}
              aria-label={label}
              aria-pressed={active}
              onClick={() => setPalette(key)}
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
      <Tooltip title={t("header.palette.custom")} mouseEnterDelay={0.35}>
        <span
          className={`${styles.option} ${isCustom ? styles.active : ""}`}
          aria-label={t("header.palette.custom")}
          aria-pressed={isCustom}
          role="button"
        >
          <ColorPicker
            value={isCustom ? customColor : undefined}
            onChangeComplete={(color: AggregationColor) => {
              setCustomColor(color.toHexString());
            }}
            disabledAlpha
          >
            <span
              className={`${styles.swatch} ${styles.customSwatch}`}
              style={isCustom ? { backgroundColor: customColor } : undefined}
              aria-hidden
            />
          </ColorPicker>
        </span>
      </Tooltip>
    </div>
  );
}
