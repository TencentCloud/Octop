import type { TFunction } from "i18next";

import { message } from "@/utils/antdMessage";
import {
  connectorsApi,
  type ConnectorInstance,
  type OAuthPendingResult,
  type OAuthStartTarget,
} from "../../../api/modules/connectors";
import { parseApiError } from "../../../utils/apiError";
import {
  isAuthPopupBlocked,
  navigateAuthWindow,
  tryOpenAuthPopup,
} from "./openAuthWindow";

/** How an authorization the dashboard started ended. */
export type ConnectorOAuthOutcome =
  | { status: "ok"; result: OAuthPendingResult }
  | { status: "cancelled" }
  | { status: "error"; message?: string }
  | { status: "timeout" }
  | { status: "blocked" };

export const CONNECTOR_AUTH_REQUIRED = "CONNECTOR_AUTH_REQUIRED";

const POLL_MS = 1500;
const TIMEOUT_MS = 5 * 60 * 1000;

/** Map a claimed pending result to an outcome (older servers send no status). */
export function pendingOutcome(
  pending: OAuthPendingResult,
): ConnectorOAuthOutcome {
  if (pending.status === "cancelled") return { status: "cancelled" };
  if (pending.status === "error") {
    return { status: "error", message: pending.message ?? undefined };
  }
  return { status: "ok", result: pending };
}

/** Tell the user how an authorization that did not succeed ended. */
export function reportOAuthOutcome(
  outcome: ConnectorOAuthOutcome,
  t: TFunction,
): void {
  switch (outcome.status) {
    case "ok":
      return;
    case "cancelled":
      message.info(t("connectors.oauthCancelled", "已取消授权"));
      return;
    case "blocked":
      message.error(
        t(
          "connectors.oauthPopupBlocked",
          "授权窗口被浏览器拦截，请允许本站弹出窗口后重试",
        ),
      );
      return;
    case "timeout":
      message.error(t("connectors.oauthTimedOut", "授权超时，请重试一键授权"));
      return;
    case "error":
      message.error(
        outcome.message || t("connectors.oauthFailed", "获取授权结果失败"),
      );
  }
}

/** The OAuth target that re-authorizes a custom MCP server, if the user may. */
export function reauthTarget(
  instance: ConnectorInstance,
): OAuthStartTarget | null {
  if (!instance.can_manage || instance.kind !== "custom-mcp") return null;
  return { type: "custom_mcp", server_name: instance.mcp_server_name };
}

export function needsAuthorization(instance: ConnectorInstance): boolean {
  return (
    instance.auth_status === "required" || instance.auth_status === "expired"
  );
}

/**
 * Connectors a failed chat turn was waiting for.
 *
 * ``servers`` comes from the error details when the turn just failed; a
 * reloaded conversation has no details, so every connector that needs
 * authorization is a candidate. Ones the user can fix come first.
 */
export function connectorsAwaitingAuth(
  instances: ConnectorInstance[],
  servers?: readonly string[] | null,
): ConnectorInstance[] {
  const wanted = servers && servers.length > 0 ? new Set(servers) : null;
  return instances
    .filter(
      (item) =>
        needsAuthorization(item) &&
        (wanted === null || wanted.has(item.mcp_server_name)),
    )
    .sort((a, b) => Number(b.can_manage) - Number(a.can_manage));
}

/** Server names listed in a ``CONNECTOR_AUTH_REQUIRED`` error, when present. */
export function authRequiredServers(details: unknown): string[] {
  if (!details || typeof details !== "object") return [];
  const connectors = (details as { connectors?: unknown }).connectors;
  if (!Array.isArray(connectors)) return [];
  return connectors
    .map((item) =>
      item && typeof item === "object"
        ? String((item as { server?: unknown }).server ?? "")
        : "",
    )
    .filter(Boolean);
}

/**
 * Run the OAuth flow for one connector in a popup and resolve with the outcome.
 *
 * Call it directly from a click handler: the popup is opened synchronously,
 * before any await, so the browser does not block it. ``target`` may be a
 * promise when it still has to be looked up.
 */
export function runConnectorOAuth(
  target: OAuthStartTarget | Promise<OAuthStartTarget | null>,
  options: { redirectAfter?: string; timeoutMs?: number } = {},
): Promise<ConnectorOAuthOutcome> {
  const popup = tryOpenAuthPopup("", "octop-oauth", "width=520,height=720");
  if (isAuthPopupBlocked(popup)) {
    return Promise.resolve({ status: "blocked" });
  }
  return new Promise<ConnectorOAuthOutcome>((resolve) => {
    let settled = false;
    let stateId = "";
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let timeoutTimer: ReturnType<typeof setTimeout> | undefined;

    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "octop:connector-oauth") return;
      if (!stateId || event.data.state_id !== stateId) return;
      void claim();
    };

    const settle = (outcome: ConnectorOAuthOutcome) => {
      if (settled) return;
      settled = true;
      if (pollTimer !== undefined) clearInterval(pollTimer);
      if (timeoutTimer !== undefined) clearTimeout(timeoutTimer);
      window.removeEventListener("message", onMessage);
      try {
        popup?.close();
      } catch {
        // The provider page may forbid access to the window; nothing to do.
      }
      resolve(outcome);
    };

    const claim = async () => {
      if (settled || !stateId) return;
      try {
        settle(pendingOutcome(await connectorsApi.oauthPending(stateId)));
      } catch {
        // 404 until the callback has run; keep waiting.
      }
    };

    void (async () => {
      try {
        const resolved = await target;
        if (!resolved) {
          settle({ status: "error" });
          return;
        }
        const started = await connectorsApi.oauthStart(
          resolved,
          options.redirectAfter ??
            `${window.location.pathname}${window.location.search}`,
        );
        if (settled) return;
        stateId = started.state_id;
        window.addEventListener("message", onMessage);
        // Some providers set COOP, so the callback page loses window.opener;
        // polling still picks up the outcome.
        pollTimer = setInterval(() => void claim(), POLL_MS);
        timeoutTimer = setTimeout(
          () => settle({ status: "timeout" }),
          options.timeoutMs ?? TIMEOUT_MS,
        );
        navigateAuthWindow(popup, started.authorize_url);
      } catch (error) {
        settle({
          status: "error",
          message: parseApiError(error)?.message,
        });
      }
    })();
  });
}
