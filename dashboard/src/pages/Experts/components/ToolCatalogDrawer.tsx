// dashboard/src/pages/Experts/components/ToolCatalogDrawer.tsx
import { useTranslation } from "react-i18next";
import ToolsTabs from "../../Agent/Tools/ToolsTabs";
import CatalogDrawer from "./CatalogDrawer";

interface ToolCatalogDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

/** Experts drawer embedding the full Tools surface (mirrors SkillCatalogDrawer). */
export default function ToolCatalogDrawer({
  agentId,
  open,
  onClose,
}: ToolCatalogDrawerProps) {
  const { t } = useTranslation();

  return (
    <CatalogDrawer
      title={t("pageShell.tools.title")}
      open={open}
      onClose={onClose}
    >
      <ToolsTabs agentId={agentId || null} />
    </CatalogDrawer>
  );
}
