import { App } from "antd";
import { Bell } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { buildDashboardNotifyWsUrl } from "../api/modules/wsNotifications";
import { getAuthToken } from "../api/request";
import { useAgent } from "../context/AgentContext";
import { ExpertIcon } from "../pages/Experts/components/iconForName";
import {
  emitSessionEvent,
  invalidateHistory,
} from "../pages/Chat/hooks/chatStore";
import {
  claimSystemPush,
  markPushHandled,
  parseDashboardPushFrame,
  pushDedupeKey,
  readSystemNotifyPermission,
  resolvePushDelivery,
  systemNotificationTag,
  truncatePushText,
  type DashboardPushEvent,
} from "../utils/dashboardPushToast";
import { peekSystemNotifyRegistration } from "../sw-register";
import { publicUrl } from "../utils/publicUrl";
import styles from "./useDashboardPushToast.module.less";

const PING_INTERVAL_MS = 25_000;
const MAX_RETRY_MS = 15_000;

function browserStorage(): Storage | null {
  try {
    const storage = window.localStorage;
    const probe = "octop-push-probe";
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return storage;
  } catch {
    return null;
  }
}

function notificationIcon(): string {
  return new URL(publicUrl("pwa-192.png"), window.location.href).href;
}

function pushChatPath(parsed: DashboardPushEvent): string {
  return `/chat/${parsed.agent_id}/${parsed.thread_id}`;
}

function systemNotifyOptions(
  parsed: DashboardPushEvent,
): NotificationOptions & { renotify?: boolean } {
  return {
    body: truncatePushText(parsed.text),
    tag: systemNotificationTag(parsed.thread_id),
    icon: notificationIcon(),
    renotify: true,
    data: { path: pushChatPath(parsed) },
  };
}

function PushToastIcon({
  iconUrl,
  iconName,
}: {
  iconUrl?: string | null;
  iconName?: string | null;
}) {
  return (
    <span className={styles.icon}>
      {iconUrl || iconName ? (
        <ExpertIcon iconUrl={iconUrl} iconName={iconName} size={16} />
      ) : (
        <Bell size={16} />
      )}
    </span>
  );
}

/** Listen for dashboard text pushes and show a bottom-right toast. */
export function useDashboardPushToast(): void {
  const { notification } = App.useApp();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { refresh, agents } = useAgent();
  const agentsRef = useRef(agents);
  agentsRef.current = agents;
  const notificationRef = useRef(notification);
  notificationRef.current = notification;
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  const tRef = useRef(t);
  tRef.current = t;
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  useEffect(() => {
    const tabId = Math.random().toString(36).slice(2);
    let ws: WebSocket | null = null;

    const onNotifyOpen = (event: MessageEvent) => {
      const data = event.data as { type?: string; path?: string } | null;
      if (!data || data.type !== "octop-notify-open" || !data.path) return;
      window.focus();
      navigateRef.current(data.path);
    };
    navigator.serviceWorker?.addEventListener("message", onNotifyOpen);
    let closed = false;
    let retry = 0;
    let reconnectTimer: number | null = null;

    const clearReconnect = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (closed) return;
      clearReconnect();
      const delay = Math.min(1000 * 2 ** retry, MAX_RETRY_MS);
      retry += 1;
      reconnectTimer = window.setTimeout(connect, delay);
    };

    const pushTitle = (parsed: DashboardPushEvent) =>
      parsed.agent_name
        ? tRef.current("chat.pushToast.title", { name: parsed.agent_name })
        : tRef.current("chat.pushToast.titleFallback");

    const openToast = (
      parsed: DashboardPushEvent,
      extra: "enable" | "enabled" | "denied" | "none",
      noticeKey = `dash-push-${parsed.thread_id}-${Date.now()}`,
    ) => {
      const agent = agentsRef.current.find(
        (item) => item.agent_id === parsed.agent_id,
      );
      const accent = agent?.color?.trim() || "#6366f1";
      notificationRef.current.open({
        key: noticeKey,
        placement: "bottomRight",
        className: styles.notice,
        style: {
          ["--push-accent" as string]: accent,
        },
        message: (
          <span className={styles.header}>
            <PushToastIcon
              iconUrl={agent?.icon_url}
              iconName={agent?.icon_name}
            />
            <span className={styles.title}>{pushTitle(parsed)}</span>
          </span>
        ),
        description: (
          <>
            <span className={styles.body}>{truncatePushText(parsed.text)}</span>
            {extra === "enable" ? (
              <button
                type="button"
                className={styles.enable}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  if (typeof Notification === "undefined") return;
                  void Notification.requestPermission().then((result) => {
                    if (result === "granted") {
                      openToast(parsed, "enabled", noticeKey);
                    } else if (result === "denied") {
                      openToast(parsed, "denied", noticeKey);
                    }
                  });
                }}
              >
                {tRef.current("chat.pushToast.enableBackground")}
              </button>
            ) : null}
            {extra === "enabled" ? (
              <span
                className={`${styles.status} ${styles.statusEnabled}`}
                onClick={(event) => event.stopPropagation()}
              >
                {tRef.current("chat.pushToast.enabled")}
              </span>
            ) : null}
            {extra === "denied" ? (
              <span
                className={styles.status}
                onClick={(event) => event.stopPropagation()}
              >
                {tRef.current("chat.pushToast.denied")}
              </span>
            ) : null}
          </>
        ),
        duration: null,
        closable: true,
        onClick: () => {
          notificationRef.current.destroy(noticeKey);
          navigateRef.current(`/chat/${parsed.agent_id}/${parsed.thread_id}`);
        },
      });
    };

    const openConstructor = (parsed: DashboardPushEvent) => {
      if (typeof Notification === "undefined") return;
      try {
        const notice = new Notification(
          pushTitle(parsed),
          systemNotifyOptions(parsed),
        );
        notice.onclick = () => {
          window.focus();
          notice.close();
          navigateRef.current(pushChatPath(parsed));
        };
      } catch {
        // The in-page toast is already on screen.
      }
    };

    const openSystem = (parsed: DashboardPushEvent) => {
      const title = pushTitle(parsed);
      const options = systemNotifyOptions(parsed);
      // Chrome drops `new Notification()` while this tab is in the background.
      // showNotification() on the worker registration is the one it still displays.
      const ready = peekSystemNotifyRegistration();
      if (ready) {
        void ready.showNotification(title, options).catch(() => {
          openConstructor(parsed);
        });
        return;
      }
      if ("serviceWorker" in navigator) {
        void navigator.serviceWorker.ready
          .then((registration) => registration.showNotification(title, options))
          .catch(() => {
            openConstructor(parsed);
          });
        return;
      }
      openConstructor(parsed);
    };

    const rememberHandled = (key: string) => {
      const storage = browserStorage();
      if (storage) markPushHandled(storage, key);
    };

    const connect = () => {
      if (closed) return;
      const token = getAuthToken();
      if (!token) {
        scheduleReconnect();
        return;
      }
      let socket: WebSocket;
      try {
        socket = new WebSocket(buildDashboardNotifyWsUrl());
      } catch {
        scheduleReconnect();
        return;
      }
      if (ws && ws !== socket) {
        const prev = ws;
        ws = null;
        try {
          prev.close();
        } catch {
          // ignore
        }
      }
      ws = socket;
      socket.onopen = () => {
        retry = 0;
      };
      socket.onmessage = (event) => {
        let raw: unknown;
        try {
          raw = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (
          raw &&
          typeof raw === "object" &&
          (raw as { type?: string }).type === "pong"
        ) {
          return;
        }
        const parsed = parseDashboardPushFrame(raw);
        if (!parsed) return;
        void refreshRef.current({ silent: true });
        // A proactive run wrote to this thread outside the chat socket. Stale it
        // here (not in the chat page listener) so the cached page is dropped
        // even when the push lands while another route is open.
        invalidateHistory(parsed.thread_id);
        // Refresh the sidebar and the open thread's history without a reload.
        emitSessionEvent({
          kind: "sessionsChanged",
          sessionId: parsed.thread_id,
          agentId: parsed.agent_id,
        });
        const permission = readSystemNotifyPermission(
          window.isSecureContext,
          typeof Notification === "undefined" ? undefined : Notification,
        );
        const delivery = resolvePushDelivery({
          permission,
          visible: document.visibilityState === "visible",
        });
        const dedupeKey = pushDedupeKey(parsed);
        // The card stays either way, so coming back still has something to open.
        openToast(parsed, delivery.offerEnable ? "enable" : "none");
        if (document.visibilityState === "visible") {
          rememberHandled(dedupeKey);
          return;
        }
        if (!delivery.system) return;
        // Raise the OS notification in this turn. A timer would be deferred
        // until the background tab is focused, and by then we would skip it.
        if (!claimSystemPush(browserStorage(), dedupeKey, tabId)) return;
        openSystem(parsed);
      };
      socket.onclose = () => {
        if (ws !== socket) return;
        ws = null;
        if (!closed) scheduleReconnect();
      };
    };

    connect();
    const pingTimer = window.setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ type: "ping" }));
        } catch {
          // ignore
        }
      }
    }, PING_INTERVAL_MS);

    return () => {
      closed = true;
      navigator.serviceWorker?.removeEventListener("message", onNotifyOpen);
      clearReconnect();
      window.clearInterval(pingTimer);
      if (ws) {
        try {
          ws.close();
        } catch {
          // ignore
        }
      }
    };
  }, []);
}
