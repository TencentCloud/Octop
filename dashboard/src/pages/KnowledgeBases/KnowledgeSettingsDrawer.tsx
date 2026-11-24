import type { ReactNode } from "react";
import { Drawer, Tabs, type DrawerProps } from "antd";
import { useTranslation } from "react-i18next";

export function KnowledgeSettingsDrawer({
  tab,
  onTabChange,
  advanced,
  children,
  ...drawerProps
}: DrawerProps & {
  tab: string;
  onTabChange: (tab: string) => void;
  advanced: ReactNode;
}) {
  const { t } = useTranslation();

  return (
    <Drawer {...drawerProps}>
      <Tabs
        activeKey={tab}
        onChange={onTabChange}
        items={[
          {
            key: "general",
            label: t("knowledgeBases.generalSettingsTab"),
            children,
          },
          {
            key: "advanced",
            label: t("knowledgeBases.advancedSettings"),
            children: advanced,
          },
        ]}
      />
    </Drawer>
  );
}
