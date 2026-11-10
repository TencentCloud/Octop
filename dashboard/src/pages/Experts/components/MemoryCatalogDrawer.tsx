// dashboard/src/pages/Experts/components/MemoryCatalogDrawer.tsx
import { Typography } from "antd";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../../hooks/useIsMobile";
import MemoryPanel from "../../Agent/Memory/MemoryPanel";
import CatalogDrawer from "./CatalogDrawer";

interface MemoryCatalogDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
  title?: string;
}

/** Experts modal embedding the full Memory surface. */
export default function MemoryCatalogDrawer({
  agentId,
  open,
  onClose,
  title,
}: MemoryCatalogDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();

  return (
    <CatalogDrawer
      title={title ?? t("pageShell.memory.title")}
      open={open}
      onClose={onClose}
      agentId={agentId}
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
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            padding: "8px 16px",
            borderBottom: "1px solid rgba(0, 0, 0, 0.06)",
            background: "rgba(0, 0, 0, 0.02)",
            flexShrink: 0,
          }}
        >
          <Typography.Text type="secondary">
            {t("memory.mcp.endpointLabel", "MCP 接入地址")}
          </Typography.Text>
          <Typography.Text
            code
            copyable={{ text: `${window.location.origin}/mcp/memory/` }}
          >
            {`${window.location.origin}/mcp/memory/`}
          </Typography.Text>
          <Typography.Text type="secondary">
            {t(
              "memory.mcp.drawerHint",
              "客户端 Header 用 Authorization: Bearer <你的 token>；token 绑定的专家决定记忆归属。",
            )}
          </Typography.Text>
        </div>
        <MemoryPanel agentId={agentId || null} fill={!isMobile} />
      </div>
    </CatalogDrawer>
  );
}
