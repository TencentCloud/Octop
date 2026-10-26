import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Input, Space } from "antd";
import { useTranslation } from "react-i18next";
import { isDesktopShell } from "../../../utils/desktopChrome";
import { openDesktopExternal } from "../../../utils/desktopExternalLinks";
import { copyText } from "../../../utils/copyText";

type AuthorizationPage = {
  active: boolean;
  navigate: (url: string) => void;
  close: () => void;
};

/** A desktop browser handoff has no Window handle. Completion is polled by callers. */
export function useAuthorizationPage(enabled = true) {
  const current = useRef<AuthorizationPage | null>(null);
  const [link, setLink] = useState<{
    url: string;
    blocked: boolean;
    cancel?: () => void;
  } | null>(null);

  const close = useCallback(() => {
    current.current?.close();
  }, []);

  useEffect(() => {
    if (!enabled) close();
    return close;
  }, [enabled, close]);

  const begin = (onClose?: () => void): AuthorizationPage => {
    close();
    setLink(null);
    // Reserve a browser popup during the click gesture; never create a WebView popup.
    let popup: Window | null = null;
    if (!isDesktopShell()) {
      try {
        popup = window.open("", "_blank", "width=520,height=720");
      } catch {
        // Keep the authorization URL available for a second, explicit click.
      }
    }
    const page: AuthorizationPage = {
      active: true,
      navigate(url) {
        if (!page.active) return;
        const parsed = new URL(url, window.location.href);
        if (!["https:", "http:"].includes(parsed.protocol)) {
          throw new Error("Unsupported authorization URL protocol");
        }
        url = parsed.href;
        let opened = false;
        try {
          if (isDesktopShell()) {
            opened = openDesktopExternal(url);
          } else if (popup && !popup.closed) {
            popup.location.replace(url);
            opened = true;
          }
        } catch {
          // The retry/copy controls remain available if the native bridge fails.
        }
        setLink({
          url,
          blocked: !opened,
          cancel: onClose ? page.close : undefined,
        });
      },
      close() {
        if (!page.active) return;
        page.active = false;
        try {
          popup?.close();
        } catch {
          // Cross-origin or already closed.
        }
        if (current.current === page) {
          current.current = null;
          setLink(null);
        }
        onClose?.();
      },
    };
    current.current = page;
    return page;
  };

  return {
    begin,
    close,
    notice: link ? <AuthorizationPageNotice key={link.url} {...link} /> : null,
  };
}

export function AuthorizationPageNotice({
  url,
  blocked,
  cancel,
}: {
  url: string;
  blocked: boolean;
  cancel?: () => void;
}) {
  const { t } = useTranslation();
  const [copyFailed, setCopyFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  return (
    <Alert
      showIcon
      type={blocked ? "warning" : "info"}
      message={t(
        blocked
          ? "connectors.authBrowserBlocked"
          : "connectors.authBrowserContinue",
      )}
      description={
        <Space direction="vertical" style={{ width: "100%" }}>
          <span>{t("connectors.authBrowserHelp")}</span>
          {cancel && <span>{t("connectors.authOAuthWaiting")}</span>}
          <Space wrap>
            <a
              href={url}
              // Desktop dispatches explicitly below; avoid the global _blank interceptor.
              target={isDesktopShell() ? undefined : "_blank"}
              rel="noopener noreferrer"
              onClick={(event) => {
                if (!isDesktopShell()) return;
                event.preventDefault();
                try {
                  if (!openDesktopExternal(url)) setCopyFailed(true);
                } catch {
                  setCopyFailed(true);
                }
              }}
            >
              {t("connectors.authBrowserReopen")}
            </a>
            <Button
              size="small"
              onClick={async () => {
                const ok = await copyText(url);
                setCopied(ok);
                setCopyFailed(!ok);
              }}
            >
              {t(
                copied
                  ? "connectors.authLinkCopied"
                  : "connectors.authLinkCopy",
              )}
            </Button>
            {cancel && (
              <Button size="small" onClick={cancel}>
                {t("connectors.authBrowserCancel")}
              </Button>
            )}
          </Space>
          {copyFailed && (
            <>
              <span>{t("connectors.authLinkManualCopy")}</span>
              <Input.TextArea
                aria-label={t("connectors.authLinkCopy")}
                value={url}
                readOnly
                onFocus={(event) => event.target.select()}
              />
            </>
          )}
        </Space>
      }
    />
  );
}
