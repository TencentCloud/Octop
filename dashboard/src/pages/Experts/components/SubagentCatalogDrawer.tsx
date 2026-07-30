import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../../hooks/useIsMobile";
import SubagentManager from "./SubagentManager";
import CatalogDrawer from "./CatalogDrawer";

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
    <CatalogDrawer
      title={t("subagents.catalogTitle")}
      open={open}
      onClose={onClose}
      mobileBodyPadding={0}
    >
      <SubagentManager
        agentId={agentId}
        agentState={agentState}
        installedSlugs={installedSlugs}
        onInstalled={onInstalled}
        fillHeight={isMobile}
      />
    </CatalogDrawer>
  );
}
