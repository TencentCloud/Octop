import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { useTheme } from "../context/ThemeContext";
import { PALETTE_SWATCH, VALID_PALETTES } from "../styles/themePalettes";
import styles from "./PaletteSwitcher.module.less";

export default function PaletteSwitcher() {
  const { palette, setPalette } = useTheme();
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
    </div>
  );
}
