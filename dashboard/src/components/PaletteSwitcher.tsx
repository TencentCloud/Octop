import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { useTheme, type ThemePalette } from "../context/ThemeContext";
import {
  PALETTE_SWATCH,
  VALID_PALETTES,
} from "../styles/themePalettes";

interface PaletteSwitcherProps {
  compact?: boolean;
}

export default function PaletteSwitcher({ compact }: PaletteSwitcherProps) {
  const { palette, setPalette } = useTheme();
  const { t } = useTranslation();

  const btnSize = compact ? 18 : 22;

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: compact ? 4 : 6,
      }}
    >
      {VALID_PALETTES.map((key) => {
        const active = palette === key;
        const label = t(`header.palette.${key}`);
        return (
          <Tooltip key={key} title={label} mouseEnterDelay={0.35}>
            <button
              type="button"
              aria-label={label}
              aria-pressed={active}
              onClick={() => setPalette(key as ThemePalette)}
              style={{
                width: btnSize,
                height: btnSize,
                padding: 0,
                borderRadius: "50%",
                border: active
                  ? "2px solid var(--fn-text-primary)"
                  : "2px solid transparent",
                background: PALETTE_SWATCH[key],
                boxShadow: active
                  ? "0 0 0 1px var(--fn-bg-elevated)"
                  : "inset 0 0 0 1px rgba(0,0,0,0.08)",
                cursor: "pointer",
                transition: "transform 0.15s ease, box-shadow 0.15s ease",
                transform: active ? "scale(1.08)" : "scale(1)",
              }}
            />
          </Tooltip>
        );
      })}
    </div>
  );
}
