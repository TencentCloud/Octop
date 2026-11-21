import { Segmented } from "antd";
import { useTranslation } from "react-i18next";

type Props = {
  value: string;
  onChange: (value: string) => void;
  /** Experts also split cloud-collab shadows out of local. */
  includeCloud?: boolean;
};

/** All / Local / Shared, with an optional Cloud segment on Experts. */
export function ResourceAudienceFilter({
  value,
  onChange,
  includeCloud = false,
}: Props) {
  const { t } = useTranslation();
  const options = [
    { value: "all", label: t("resourceAudience.all") },
    { value: "local", label: t("resourceAudience.local") },
    ...(includeCloud
      ? [{ value: "cloud", label: t("resourceAudience.cloud") }]
      : []),
    { value: "shared", label: t("resourceAudience.shared") },
  ];
  return (
    <Segmented
      size="small"
      value={value}
      onChange={(next) => onChange(String(next))}
      options={options}
    />
  );
}
