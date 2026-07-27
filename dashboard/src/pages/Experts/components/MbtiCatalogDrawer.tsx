/**
 * MBTI Catalog Drawer — wraps MBTISelector inside a Drawer
 * so experts page can browse and apply MBTI types without leaving the page.
 */
import { Drawer } from "antd";
import { useTranslation } from "react-i18next";
import MBTISelector from "../../Agent/Personalization/components/MBTISelector";

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
    <Drawer
      title={t("personalization.mbti.catalogTitle")}
      open={open}
      onClose={onClose}
      width="min(1080px, 92vw)"
      destroyOnHidden
      styles={{ body: { padding: "16px 20px 20px" } }}
    >
      {agentId ? (
        <MBTISelector
          key={agentId}
          showHeader={false}
          agentId={agentId}
          onApplied={onApplied}
        />
      ) : null}
    </Drawer>
  );
}
