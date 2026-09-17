import { useTranslation } from "react-i18next";
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

  return (
    <CatalogDrawer
      title={t("subagents.catalogTitle")}
      open={open}
      onClose={onClose}
      mobileBodyPadding={0}
    >
      {/* Same scroll shell as ChannelCatalogDrawer — desktop used to clip (~12 cards). */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
        }}
      >
        <SubagentManager
          agentId={agentId}
          agentState={agentState}
          installedSlugs={installedSlugs}
          onInstalled={onInstalled}
          fillHeight
        />
      </div>
    </CatalogDrawer>
  );
}
