import type { ReactNode } from "react";
import { Button, Input, Space, Tooltip, Typography } from "antd";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import SsoProviderCard from "./SsoProviderCard";
import styles from "./index.module.less";

interface SsoAppProviderShellProps {
  kind: string;
  title: string;
  description: string;
  statusLabel: ReactNode;
  enableSwitch: ReactNode;
  redirectUri: string;
  redirectHint: string;
  redirectDocs?: string;
  copied: boolean;
  onCopyRedirect: () => void;
  asideExtra?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

/** Shared admin shell for App ID / App Secret OAuth providers (Feishu, WeCom, …). */
export default function SsoAppProviderShell({
  kind,
  title,
  description,
  statusLabel,
  enableSwitch,
  redirectUri,
  redirectHint,
  redirectDocs,
  copied,
  onCopyRedirect,
  asideExtra,
  defaultOpen = false,
  children,
}: SsoAppProviderShellProps) {
  const { t } = useTranslation();

  return (
    <SsoProviderCard
      kind={kind}
      title={title}
      description={description}
      defaultOpen={defaultOpen}
      extra={
        <>
          {statusLabel}
          {enableSwitch}
        </>
      }
    >
      <div className={styles.ssoLayout}>
        <aside className={styles.ssoAside}>
          <section className={styles.ssoRedirectCard}>
            <div className={styles.ssoRedirectHeader}>
              <h4 className={styles.ssoSectionTitle}>
                {t("adminSso.redirectUri")}
              </h4>
              <p className={styles.ssoSectionHint}>{redirectHint}</p>
            </div>
            <Space.Compact className={styles.ssoRedirectRow}>
              <Tooltip title={redirectUri || undefined}>
                <Input
                  readOnly
                  value={redirectUri}
                  className={styles.ssoRedirectInput}
                  placeholder={t("adminSso.redirectUriEmpty")}
                />
              </Tooltip>
              <Button
                type="primary"
                icon={copied ? <Check size={15} /> : <Copy size={15} />}
                onClick={onCopyRedirect}
                disabled={!redirectUri}
                aria-label={t("adminSso.copyRedirectUri")}
              >
                {copied ? t("adminSso.copied") : t("adminSso.copy")}
              </Button>
            </Space.Compact>
            {redirectDocs ? (
              <Typography.Paragraph
                type="secondary"
                className={styles.ssoRedirectDocs}
              >
                {redirectDocs}
              </Typography.Paragraph>
            ) : null}
          </section>

          {asideExtra}
        </aside>

        <div>{children}</div>
      </div>
    </SsoProviderCard>
  );
}
