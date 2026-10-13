import type { CSSProperties, ReactNode } from "react";
import { Alert, Drawer } from "antd";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../../hooks/useIsMobile";
import styles from "../index.module.less";

interface CatalogDrawerProps {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Desktop drawer width. Mobile is always full width. */
  width?: string;
  /** Mobile body padding (Subagents uses 0 for edge-to-edge). */
  mobileBodyPadding?: CSSProperties["padding"];
  /** When this is a Bridge shadow expert, show the remote-edit banner. */
  agentId?: string | null;
  /** Extra i18n key under ``chat.remoteExpert`` for surfaces that cannot fully tunnel. */
  remoteHintKey?: string;
}

/**
 * Shared Experts "catalog" Drawer chrome (skills / tools / memory / subagents / channels / MBTI).
 */
export default function CatalogDrawer({
  title,
  open,
  onClose,
  children,
  width = "min(1080px, 92vw)",
  mobileBodyPadding = "12px 14px 16px",
  agentId,
  remoteHintKey,
}: CatalogDrawerProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const remote = Boolean(agentId?.startsWith("bridge:"));

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      width={isMobile ? "100%" : width}
      destroyOnHidden
      // Flex height chain on every viewport so overflow:auto children can scroll
      // (desktop used to clip long catalogs — see #136 / #340).
      rootClassName={
        isMobile
          ? `${styles.catalogDrawerFlex} ${styles.catalogDrawerRoot}`
          : styles.catalogDrawerFlex
      }
      styles={{
        body: {
          padding: isMobile ? mobileBodyPadding : "16px 20px 20px",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          minHeight: 0,
          flex: 1,
        },
      }}
    >
      {remote ? (
        <Alert
          type="info"
          showIcon
          message={t("chat.remoteExpert.editBanner")}
          description={
            remoteHintKey ? t(`chat.remoteExpert.${remoteHintKey}`) : undefined
          }
          style={{ marginBottom: 12, flexShrink: 0 }}
        />
      ) : null}
      {children}
    </Drawer>
  );
}
