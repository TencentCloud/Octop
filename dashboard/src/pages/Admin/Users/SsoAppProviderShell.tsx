import type { ReactNode } from "react";
import { Button, Input, Space, Tooltip, Typography } from "antd";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";
import SsoProviderCard from "./SsoProviderCard";
import styles from "./index.module.less";

const OAUTH_GUIDE_STEPS = [
  "adminSso.oauthGuideStep1",
  "adminSso.oauthGuideStep2",
  "adminSso.oauthGuideStep3",
  "adminSso.oauthGuideStep4",
  "adminSso.oauthGuideStep5",
] as const;

interface SsoAppProviderShellProps {
  kind: string;
  title: string;
  description: string;
  statusLabel: ReactNode;
  enableSwitch: ReactNode;
  redirectUri: string;
  redirectHint: string;
  redirectDocs?: string;
  /** Host-only domain for providers like WeCom (“授权回调域”). */
  callbackDomain?: string;
  callbackDomainHint?: string;
  copied: boolean;
  copiedDomain?: boolean;
  onCopyRedirect: () => void;
  onCopyDomain?: () => void;
  asideExtra?: ReactNode;
  defaultOpen?: boolean;
  /** When true, render as a full tab surface (no Collapse). */
  standalone?: boolean;
  /** Checklist progress 0–5 (same model as OIDC aside). */
  guideStep?: number;
  enabled?: boolean;
  previewName?: string;
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
  callbackDomain,
  callbackDomainHint,
  copied,
  copiedDomain = false,
  onCopyRedirect,
  onCopyDomain,
  asideExtra,
  defaultOpen = false,
  standalone = false,
  guideStep = 0,
  enabled = false,
  previewName = "",
  children,
}: SsoAppProviderShellProps) {
  const { t } = useTranslation();
  const previewLabel = previewName.trim() || t("adminSso.statusUnnamed");

  const body = (
    <div className={styles.ssoLayout}>
      <aside className={styles.ssoAside}>
        <div className={styles.ssoGuide}>
          <div className={styles.ssoAsideTitle}>{t("adminSso.guideTitle")}</div>
          <ol className={styles.ssoGuideList}>
            {OAUTH_GUIDE_STEPS.map((key, index) => {
              const done = guideStep > index;
              const current = guideStep === index;
              return (
                <li
                  key={key}
                  className={[
                    styles.ssoGuideItem,
                    done ? styles.ssoGuideDone : "",
                    current ? styles.ssoGuideCurrent : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <span className={styles.ssoGuideIndex} aria-hidden>
                    {done ? <Check size={12} /> : index + 1}
                  </span>
                  <span>{t(key)}</span>
                </li>
              );
            })}
          </ol>
        </div>

        <div className={styles.ssoAsideCard}>
          <div className={styles.ssoAsideTitle}>
            {t("adminSso.loginPreview")}
          </div>
          <div
            className={[
              styles.ssoPreviewBtn,
              enabled ? "" : styles.ssoPreviewBtnMuted,
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {t("login.oidcWith", { name: previewLabel })}
          </div>
          {!enabled && (
            <p className={styles.ssoPreviewHint}>
              {t("adminSso.loginPreviewDisabled")}
            </p>
          )}
        </div>

        <section className={styles.ssoRedirectCard}>
          <div className={styles.ssoRedirectHeader}>
            <h4 className={styles.ssoSectionTitle}>
              {t("adminSso.redirectUri")}
            </h4>
            <p className={styles.ssoSectionHint}>{redirectHint}</p>
          </div>
          {callbackDomain ? (
            <>
              <p className={styles.ssoSectionHint}>
                {callbackDomainHint || t("adminSso.callbackDomainHint")}
              </p>
              <Space.Compact className={styles.ssoRedirectRow}>
                <Tooltip title={callbackDomain}>
                  <Input
                    readOnly
                    value={callbackDomain}
                    className={styles.ssoRedirectInput}
                  />
                </Tooltip>
                <Button
                  type="primary"
                  icon={copiedDomain ? <Check size={15} /> : <Copy size={15} />}
                  onClick={onCopyDomain}
                  aria-label={t("adminSso.copyCallbackDomain")}
                >
                  {copiedDomain ? t("adminSso.copied") : t("adminSso.copy")}
                </Button>
              </Space.Compact>
              <p className={styles.ssoSectionHint}>
                {t("adminSso.callbackFullUriHint")}
              </p>
            </>
          ) : null}
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
  );

  if (standalone) {
    return (
      <div className={styles.ssoStandalone}>
        <div className={styles.ssoStandaloneToolbar}>
          <div className={styles.ssoStandaloneMeta}>
            <span className={styles.ssoKindBadge}>{kind}</span>
            {statusLabel}
          </div>
          {enableSwitch}
        </div>
        {body}
      </div>
    );
  }

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
      {body}
    </SsoProviderCard>
  );
}
