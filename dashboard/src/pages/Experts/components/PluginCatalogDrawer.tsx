// dashboard/src/pages/Experts/components/PluginCatalogDrawer.tsx
import { useTranslation } from "react-i18next";
import AgentPluginsPanel from "../../Agent/Personalization/components/AgentPluginsPanel";
import CatalogDrawer from "./CatalogDrawer";

interface PluginCatalogDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

/** Experts drawer embedding the agent plugins surface (mirrors ToolCatalogDrawer). */
export default function PluginCatalogDrawer({
  agentId,
  open,
  onClose,
}: PluginCatalogDrawerProps) {
  const { t } = useTranslation();

  return (
    <CatalogDrawer
      title={t("personalization.tabs.plugins")}
      open={open}
      onClose={onClose}
    >
      <AgentPluginsPanel agentId={agentId || null} />
    </CatalogDrawer>
  );
}
