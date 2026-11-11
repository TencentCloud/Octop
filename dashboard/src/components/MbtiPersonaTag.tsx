import { Tag, Tooltip } from "antd";
import { useTranslation } from "react-i18next";

interface MbtiPersonaTagProps {
  value: string | null | undefined;
  /** Show a placeholder tag when MBTI is not set. */
  showDefault?: boolean;
  /** Click handler — when provided, the tag becomes clickable. */
  onClick?: () => void;
}

export default function MbtiPersonaTag({
  value,
  showDefault = true,
  onClick,
}: MbtiPersonaTagProps) {
  const { t } = useTranslation();

  if (!value && !showDefault) return null;

  const code = value?.toUpperCase() ?? "";
  const localizedName = code && t(`mbti.${code}`, { defaultValue: "" });
  const label = code
    ? localizedName
      ? `${code} ${localizedName}`
      : code
    : t("experts.mbtiUnset");
  const clickable = !!onClick;
  const tooltipTitle = value
    ? clickable
      ? t("experts.mbtiViewDetail")
      : t("nav.mbti")
    : clickable
    ? t("experts.mbtiSetHint")
    : t("nav.mbti");

  const tag = (
    <Tag
      color={value ? "purple" : "default"}
      style={{
        margin: 0,
        cursor: clickable ? "pointer" : undefined,
      }}
      onClick={
        clickable
          ? (e) => {
              e.stopPropagation();
              onClick();
            }
          : undefined
      }
    >
      {label}
    </Tag>
  );

  return <Tooltip title={tooltipTitle}>{tag}</Tooltip>;
}
