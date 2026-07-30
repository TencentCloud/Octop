// dashboard/src/pages/Experts/components/MemoryCatalogDrawer.tsx
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../../hooks/useIsMobile";
import MemoryPanel from "../../Agent/Memory/MemoryPanel";
import CatalogDrawer from "./CatalogDrawer";

interface MemoryCatalogDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

/** Experts modal embedding the full Memory surface. */
export default function MemoryCatalogDrawer({
  agentId,
  open,
  onClose,
}: MemoryCatalogDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();

  return (
    <CatalogDrawer
      title={t("pageShell.memory.title")}
      open={open}
      onClose={onClose}
    >
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <MemoryPanel agentId={agentId || null} fill={!isMobile} />
      </div>
    </CatalogDrawer>
  );
}
