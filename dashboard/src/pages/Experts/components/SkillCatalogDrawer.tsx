// dashboard/src/pages/Experts/components/SkillCatalogDrawer.tsx
import { useTranslation } from "react-i18next";
import SkillsTabs from "../../Agent/Skills/components/SkillsTabs";
import CatalogDrawer from "./CatalogDrawer";

interface SkillCatalogDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

/** Experts modal embedding the full Skills surface. */
export default function SkillCatalogDrawer({
  agentId,
  open,
  onClose,
}: SkillCatalogDrawerProps) {
  const { t } = useTranslation();

  return (
    <CatalogDrawer
      title={t("pageShell.skills.title")}
      open={open}
      onClose={onClose}
    >
      <SkillsTabs agentId={agentId || null} />
    </CatalogDrawer>
  );
}
