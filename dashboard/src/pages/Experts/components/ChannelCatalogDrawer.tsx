import { useTranslation } from "react-i18next";
import ChannelsPanel from "../../Agent/Channels/ChannelsPanel";
import CatalogDrawer from "./CatalogDrawer";

interface ChannelCatalogDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

/** Experts modal embedding the Channels surface. */
export default function ChannelCatalogDrawer({
  agentId,
  open,
  onClose,
}: ChannelCatalogDrawerProps) {
  const { t } = useTranslation();

  return (
    <CatalogDrawer
      title={t("pageShell.channels.title")}
      open={open}
      onClose={onClose}
    >
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
        }}
      >
        <ChannelsPanel agentId={agentId || null} />
      </div>
    </CatalogDrawer>
  );
}
