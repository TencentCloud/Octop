import { useEffect, useRef, useState } from "react";
import { Button, Result, Spin } from "antd";
import { message } from "@/utils/antdMessage";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { setAuthToken } from "../../api";
import { authApi } from "../../api/modules/auth";
import { refreshServerLabels } from "../../i18n";
import { apiErrorMessage } from "../../utils/apiError";
import { applyUserLocale } from "../../utils/locale";

const DEFAULT_REDIRECT = "/chat";

/** Return an internal destination, never an absolute or protocol-relative URL. */
export function safeRedirect(path: string | null): string {
  if (
    !path ||
    !path.startsWith("/") ||
    path.startsWith("//") ||
    path.includes("\\") ||
    path.includes("://") ||
    path.startsWith("http:")
  ) {
    return DEFAULT_REDIRECT;
  }
  return path;
}

/** Prefer URL fragment (not sent to servers); fall back to query for old links. */
export function readOidcCompleteParams(
  hash: string,
  search: string,
): { code: string | null; redirect: string | null } {
  const fromHash = new URLSearchParams(
    hash.startsWith("#") ? hash.slice(1) : hash,
  );
  const fromQuery = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );
  return {
    code: fromHash.get("code") || fromQuery.get("code"),
    redirect: fromHash.get("redirect") || fromQuery.get("redirect"),
  };
}

export default function OidcComplete() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const did = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (did.current) return;
    did.current = true;

    const { code, redirect } = readOidcCompleteParams(
      window.location.hash,
      window.location.search,
    );
    if (!code) {
      const text = t("login.oidcComplete.missingCode");
      setError(text);
      message.error(text);
      return;
    }

    // Drop credentials from the address bar before the network exchange.
    if (window.location.hash || window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }

    void authApi
      .exchangeOidcCode(code)
      .then(async (res) => {
        setAuthToken(res.access_token);
        await applyUserLocale(res.user.locale);
        void refreshServerLabels(res.user.locale);
        navigate(safeRedirect(redirect), { replace: true });
      })
      .catch((err) => {
        const text = apiErrorMessage(err, t("login.oidcComplete.failed"), t);
        setError(text);
        message.error(text);
      });
  }, [navigate, t]);

  if (error) {
    return (
      <Result
        status="error"
        title={t("login.oidcComplete.title")}
        subTitle={error}
        extra={
          <Button
            type="primary"
            onClick={() => navigate("/login", { replace: true })}
          >
            {t("login.oidcComplete.backToLogin")}
          </Button>
        }
      />
    );
  }

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Spin size="large" tip={t("login.oidcComplete.loading")} />
    </div>
  );
}
