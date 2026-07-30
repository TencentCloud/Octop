/**
 * MBTI Catalog Drawer — wraps MBTISelector inside a Drawer
 * so experts page can browse and apply MBTI types without leaving the page.
 */
import { useTranslation } from "react-i18next";
import MBTISelector from "../../Agent/Personalization/components/MBTISelector";
import CatalogDrawer from "./CatalogDrawer";

interface MbtiCatalogDrawerProps {
  open: boolean;
  agentId: string | null;
  onClose: () => void;
  onApplied: () => void;
}

export default function MbtiCatalogDrawer({
  open,
  agentId,
  onClose,
  onApplied,
}: MbtiCatalogDrawerProps) {
  const { t } = useTranslation();

  return (
    <CatalogDrawer
      title={t("personalization.mbti.catalogTitle")}
      open={open}
      onClose={onClose}
    >
      {agentId ? (
        <MBTISelector
          key={agentId}
          showHeader={false}
          agentId={agentId}
          onApplied={onApplied}
        />
      ) : null}
    </CatalogDrawer>
  );
}
