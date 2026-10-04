import { Monitor, Sun, Moon } from "lucide-react";
import { useTheme } from "../context/ThemeContext";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";

type ThemePreference = "system" | "light" | "dark";

const options: { key: ThemePreference; Icon: typeof Monitor }[] = [
  { key: "system", Icon: Monitor },
  { key: "light", Icon: Sun },
  { key: "dark", Icon: Moon },
];

interface ThemeSwitcherProps {
  compact?: boolean;
}

export default function ThemeSwitcher({ compact }: ThemeSwitcherProps) {
  const { preference, setPreference } = useTheme();
  const { t } = useTranslation();

  const labelMap: Record<ThemePreference, string> = {
    system: t("header.themeSystem"),
    light: t("header.themeLight"),
    dark: t("header.themeDark"),
  };

  const btnSize = compact ? 26 : 32;
  const iconSize = compact ? 14 : 16;

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 2,
        padding: compact ? 2 : 3,
        borderRadius: "var(--fn-radius-full, 999px)",
        background: "var(--fn-bg-tertiary)",
      }}
    >
      {options.map(({ key, Icon }) => {
        const active = preference === key;
        return (
          <Tooltip key={key} title={labelMap[key]} mouseEnterDelay={0.4}>
            <button
              type="button"
              aria-label={labelMap[key]}
              aria-pressed={active}
              onClick={() => setPreference(key)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: btnSize,
                height: btnSize,
                border: "none",
                borderRadius: "var(--fn-radius-full, 999px)",
                background: active ? "var(--fn-bg-elevated)" : "transparent",
                color: active
                  ? "var(--fn-text-primary)"
                  : "var(--fn-text-secondary)",
                boxShadow: active ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
            >
              <Icon size={iconSize} strokeWidth={1.8} />
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
