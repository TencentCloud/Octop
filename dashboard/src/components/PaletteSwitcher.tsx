import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { useTheme } from "../context/ThemeContext";
import {
  DEFAULT_CUSTOM_COLOR,
  PALETTE_SWATCH,
  VALID_PALETTES,
} from "../styles/themePalettes";
import styles from "./PaletteSwitcher.module.less";

/** Curated 8-swatch brand palette picker + a custom color picker. */
export default function PaletteSwitcher() {
  const { palette, setPalette, customColor, setCustomColor } = useTheme();
  const { t } = useTranslation();

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
        <button
          type="button"
          className={`${styles.option} ${
            palette === "custom" ? styles.active : ""
          }`}
          aria-label={t("header.palette.custom")}
          aria-pressed={palette === "custom"}
          onClick={() => setPalette("custom")}
        >
          <span
            className={styles.swatch}
            style={{ backgroundColor: customColor || DEFAULT_CUSTOM_COLOR }}
            aria-hidden
          />
        </button>
      </Tooltip>
      <Tooltip title={t("header.palette.customPicker")} mouseEnterDelay={0.35}>
        <span className={styles.customPickerWrap}>
          <input
            type="color"
            className={styles.customPickerInput}
            value={customColor || DEFAULT_CUSTOM_COLOR}
            aria-label={t("header.palette.customPicker")}
            onChange={(e) => setCustomColor(e.target.value)}
            onInput={(e) => setCustomColor(e.currentTarget.value)}
          />
        </span>
      </Tooltip>
    </div>
  );
}
