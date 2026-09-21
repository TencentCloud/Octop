import { useTranslation } from "react-i18next";
import SubagentManager from "./SubagentManager";
import CatalogDrawer from "./CatalogDrawer";

interface SubagentCatalogDrawerProps {
  agentId: string;
  agentState: string;
  open: boolean;
  installedSlugs: Set<string>;
  initialTab?: string;
  onClose: () => void;
  onInstalled: () => void;
}

export default function SubagentCatalogDrawer({
  agentId,
  agentState,
  open,
  installedSlugs,
  initialTab,
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
      {/*
        Flex column + overflow:hidden so fillHeight SubagentManager gets a
        bounded height and owns scrolling. A plain overflow:auto shell left the
        inner catalogDrawerMobile unconstrained; overscroll-behavior:contain then
        ate wheel events and desktop scroll appeared broken.
      */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <SubagentManager
          key={initialTab ?? "installed"}
          agentId={agentId}
          agentState={agentState}
          installedSlugs={installedSlugs}
          initialTab={initialTab}
          onInstalled={onInstalled}
          fillHeight
        />
      </div>
    </CatalogDrawer>
  );
}
