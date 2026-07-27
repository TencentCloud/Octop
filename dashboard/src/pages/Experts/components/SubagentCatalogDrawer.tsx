import { Drawer } from "antd";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../../hooks/useIsMobile";
import SubagentManager from "./SubagentManager";
import styles from "../index.module.less";

interface SubagentCatalogDrawerProps {
  agentId: string;
  agentState: string;
  open: boolean;
  installedSlugs: Set<string>;
  onClose: () => void;
  onInstalled: () => void;
}

export default function SubagentCatalogDrawer({
  agentId,
  agentState,
  open,
  installedSlugs,
  onClose,
  onInstalled,
}: SubagentCatalogDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();

  return (
    <Drawer
      title={t("subagents.catalogTitle")}
      open={open}
      onClose={onClose}
      width={isMobile ? "100%" : "min(1080px, 92vw)"}
      destroyOnHidden
      rootClassName={isMobile ? styles.catalogDrawerRoot : undefined}
      styles={{
        body: isMobile
          ? {
              padding: 0,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }
          : { padding: "16px 20px 20px" },
      }}
    >
      <SubagentManager
        agentId={agentId}
        agentState={agentState}
        installedSlugs={installedSlugs}
        onInstalled={onInstalled}
        fillHeight={isMobile}
      />
    </Drawer>
  );
}
