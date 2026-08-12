import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import {
  PALETTE_SWATCH,
  VALID_PALETTES,
  type ThemePalette,
} from "../styles/themePalettes";
import styles from "./PaletteSwitcher.module.less";

interface ExpertColorPickerProps {
  value: ThemePalette;
  onChange: (palette: ThemePalette) => void;
}

/** Curated 8-swatch picker for expert/agent accent color (list cards). */
export default function ExpertColorPicker({
  value,
  onChange,
}: ExpertColorPickerProps) {
  const { t } = useTranslation();

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
    </div>
  );
}
