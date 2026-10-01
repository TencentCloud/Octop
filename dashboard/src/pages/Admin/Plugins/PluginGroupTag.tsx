import { Tag } from "antd";
import { useTranslation } from "react-i18next";
import { isKnownPluginGroup } from "./pluginGroups";

/** Colored chip for ``plugin.yaml`` ``group`` on admin / tools cards. */
export function PluginGroupTag({ group }: { group?: string | null }) {
  const { t } = useTranslation();
  const slug = (group || "").trim().toLowerCase();
  if (!slug) return null;
  const label = isKnownPluginGroup(slug)
    ? t(`plugins.groups.${slug}`)
    : t("plugins.groupUnknown");
  return <Tag bordered={false}>{label}</Tag>;
}
