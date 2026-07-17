// dashboard/src/pages/Experts/components/SkillCatalogDrawer.tsx
import { Drawer } from "antd";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../../hooks/useIsMobile";
import SkillsTabs from "../../Agent/Skills/components/SkillsTabs";
import styles from "../index.module.less";

interface SkillCatalogDrawerProps {
  agentId: string;
  open: boolean;
  onClose: () => void;
}

// Reusable "expert modal" (专家弹框) embedding the full Skills surface
// (已安装 / 内置 / 技能市场) — the exact same tabs as the /skills page.
export default function SkillCatalogDrawer({
  agentId,
  open,
  onClose,
}: SkillCatalogDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();

  return (
    <Drawer
      title={t("pageShell.skills.title")}
      open={open}
      onClose={onClose}
      width={isMobile ? "100%" : "min(1080px, 92vw)"}
      destroyOnClose
      rootClassName={isMobile ? styles.catalogDrawerRoot : undefined}
      styles={{
        body: {
          padding: isMobile ? "12px 14px 16px" : "16px 20px 20px",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
      }}
    >
      <SkillsTabs agentId={agentId || null} />
    </Drawer>
  );
}
