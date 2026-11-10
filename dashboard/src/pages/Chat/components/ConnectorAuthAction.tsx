import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";

import { message } from "@/utils/antdMessage";
import {
  connectorsApi,
  type ConnectorInstance,
} from "../../../api/modules/connectors";
import {
  authRequiredServers,
  connectorsAwaitingAuth,
  reauthTarget,
  reportOAuthOutcome,
  runConnectorOAuth,
} from "../../Agent/Connectors/connectorOAuth";
import styles from "../index.module.less";

interface ConnectorAuthActionProps {
  /** ``details`` of the ``CONNECTOR_AUTH_REQUIRED`` error, when the turn just failed. */
  details?: unknown;
  /** Re-send the turn that failed. */
  onAuthorized?: () => void;
}

/**
 * "Authorize" button for a chat turn that failed because a connector needs
 * OAuth. The provider opens in a popup; when it reports success the failed
 * turn is sent again, so the user does not have to repeat themselves.
 */
export function ConnectorAuthAction({
  details,
  onAuthorized,
}: ConnectorAuthActionProps) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<ConnectorInstance[] | null>(null);
  const [authorizing, setAuthorizing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    connectorsApi
      .listInstances()
      .then((instances) => {
        if (!cancelled) {
          setPending(
            connectorsAwaitingAuth(instances, authRequiredServers(details)),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setPending([]);
      });
    return () => {
      cancelled = true;
    };
  }, [details]);

  if (!pending || pending.length === 0) return null;
  const next = pending[0];
  const target = reauthTarget(next);
  if (!target) {
    return (
      <span className={styles.errorAuthHint}>
        {t("chat.connectorAuthAskOwner", {
          name: next.display_name,
          defaultValue: "「{{name}}」的授权已失效，请联系它的所有者重新授权",
        })}
      </span>
    );
  }

  const authorize = () => {
    if (authorizing) return;
    setAuthorizing(true);
    void runConnectorOAuth(target).then((outcome) => {
      setAuthorizing(false);
      if (outcome.status !== "ok") {
        reportOAuthOutcome(outcome, t);
        return;
      }
      message.success(
        t("chat.connectorAuthDone", {
          name: next.display_name,
          defaultValue: "「{{name}}」已授权，正在重新发送",
        }),
      );
      setPending((current) => current?.slice(1) ?? null);
      onAuthorized?.();
    });
  };

  return (
    <button
      className={styles.errorConfigBtn}
      onClick={authorize}
      disabled={authorizing}
      type="button"
    >
      <KeyRound size={13} />
      {authorizing
        ? t("connectors.authorizing", "正在等待授权…")
        : t("chat.connectorAuthorize", {
            name: next.display_name,
            defaultValue: "授权「{{name}}」并重试",
          })}
    </button>
  );
}

/** True for a chat error caused by a connector that needs authorization. */
export function isConnectorAuthError(
  code: unknown,
  text: string | null | undefined,
): boolean {
  return (
    code === "CONNECTOR_AUTH_REQUIRED" ||
    Boolean(text?.includes("[CONNECTOR_AUTH_REQUIRED]"))
  );
}
