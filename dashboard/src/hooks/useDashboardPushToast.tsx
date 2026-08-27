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
  parseDashboardPushFrame,
  truncatePushText,
} from "../utils/dashboardPushToast";
import styles from "./useDashboardPushToast.module.less";

const PING_INTERVAL_MS = 25_000;
const MAX_RETRY_MS = 15_000;

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
        <ExpertIcon iconUrl={iconUrl} iconName={iconName} size={18} />
      ) : (
        <Bell size={18} />
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
    let ws: WebSocket | null = null;
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
        const agent = agentsRef.current.find(
          (a) => a.agent_id === parsed.agent_id,
        );
        const accent = agent?.color?.trim() || "#6366f1";
        const title = parsed.agent_name
          ? tRef.current("chat.pushToast.title", { name: parsed.agent_name })
          : tRef.current("chat.pushToast.titleFallback");
        notificationRef.current.open({
          key: `dash-push-${parsed.thread_id}-${Date.now()}`,
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
              <span className={styles.title}>{title}</span>
            </span>
          ),
          description: (
            <span className={styles.body}>{truncatePushText(parsed.text)}</span>
          ),
          duration: null,
          closable: true,
          onClick: () => {
            navigateRef.current(`/chat/${parsed.agent_id}/${parsed.thread_id}`);
          },
        });
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
