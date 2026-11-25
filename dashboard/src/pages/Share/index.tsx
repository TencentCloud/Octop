import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "antd";
import { useTranslation } from "react-i18next";
import {
  fetchPublicShare,
  type PublicShareView,
} from "../../api/modules/octopThreads";
import { isNotFoundApiError } from "../../utils/apiError";
import { primeServerTimezone } from "../../hooks/useServerTimezone";
import { VoiceOutputProvider } from "../../context/VoiceOutputContext";
import { convertHistoryMessages } from "../Chat/hooks/useChat";
import { groupConsecutiveAssistantMessages } from "../Chat/utils/messageGrouping";
import AssistantTurnView from "../Chat/components/AssistantTurnView";
import MessageBubble from "../Chat/components/MessageBubble";
import type { MessageGroup } from "../Chat/utils/messageGrouping";
import styles from "./index.module.less";

type LoadState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error" }
  | { kind: "ready"; view: PublicShareView };

function turnLabel(group: MessageGroup): string {
  const first = group.messages[0];
  if (!first) return "";
  if (first.role === "user") return first.author?.displayName?.trim() || "";
  return (
    group.messages.find((item) => item.speakerFace?.name)?.speakerFace?.name?.trim() ||
    group.messages.find((item) => item.speakerAgentId)?.speakerAgentId?.trim() ||
    ""
  );
}

export default function SharePage() {
  const { shareId = "" } = useParams();
  const { t } = useTranslation();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async () => {
    if (!shareId) {
      setState({ kind: "missing" });
      return;
    }
    setState({ kind: "loading" });
    try {
      const view = await fetchPublicShare(shareId);
      setState({ kind: "ready", view });
    } catch (error) {
      setState({ kind: isNotFoundApiError(error) ? "missing" : "error" });
    }
  }, [shareId]);

  useEffect(() => {
    void load();
  }, [load]);

  const title =
    state.kind === "ready"
      ? state.view.title || t("chat.sharePage.fallbackTitle")
      : t("chat.sharePage.fallbackTitle");

  useEffect(() => {
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);

  const groups = useMemo(() => {
    if (state.kind !== "ready") return [];
    primeServerTimezone(state.view.timezone);
    const faces = state.view.messages
      .filter((message) => message.role === "assistant")
      .map((message) => ({
        name: message.speaker_name || state.view.agent_name,
        iconUrl: message.speaker_icon_url ?? null,
        iconName: message.speaker_icon_name ?? null,
        color: message.speaker_color ?? null,
      }));
    const converted = convertHistoryMessages(
      state.view.messages.map((message) => ({
        role: message.role,
        content: message.content,
        timestamp: message.timestamp,
        decision: message.decision,
        author:
          message.role === "user"
            ? {
                user_id: 1,
                display_name: message.author_name || t("chat.sharePage.user"),
                username: "",
                avatar_icon: message.author_avatar_icon || null,
                avatar_url: message.author_avatar_url || null,
              }
            : undefined,
      })),
    );
    let faceIdx = 0;
    let currentFace = faces[0] ?? {
      name: state.view.agent_name,
      iconUrl: null,
      iconName: null,
      color: null,
    };
    const messages = converted.map((message) => {
      if (message.role === "assistant") {
        currentFace = faces[faceIdx] ?? currentFace;
        faceIdx += 1;
        return { ...message, speakerFace: currentFace };
      }
      if (message.role === "tool") {
        return { ...message, speakerFace: currentFace };
      }
      return message;
    });
    return groupConsecutiveAssistantMessages(messages);
  }, [state, t]);

  return (
    <div className={styles.shell}>
      <div className={styles.column}>
        <header className={styles.header}>
          <div>
            <h1 className={styles.title}>{title}</h1>
            {state.kind === "ready" && state.view.agent_name ? (
              <p className={styles.agent}>{state.view.agent_name}</p>
            ) : null}
          </div>
          <span className={styles.badge}>{t("chat.sharePage.readonly")}</span>
        </header>

        {state.kind === "loading" ? (
          <p className={styles.state}>{t("common.loading", "加载中…")}</p>
        ) : null}

        {state.kind === "missing" ? (
          <p className={styles.state}>{t("chat.sharePage.notFound")}</p>
        ) : null}

        {state.kind === "error" ? (
          <div className={styles.state}>
            <p>{t("chat.sharePage.loadFailed")}</p>
            <Button onClick={() => void load()}>{t("common.retry")}</Button>
          </div>
        ) : null}

        {state.kind === "ready" ? (
          <VoiceOutputProvider>
            {!state.view.ready ? (
              <p className={styles.note}>{t("chat.sharePage.preparing")}</p>
            ) : null}
            {state.view.truncated ? (
              <p className={styles.note}>{t("chat.sharePage.truncated")}</p>
            ) : null}
            {groups.length === 0 ? (
              state.view.ready ? (
                <p className={styles.state}>{t("chat.sharePage.empty")}</p>
              ) : null
            ) : (
              <div className={styles.transcript}>
                {groups.map((group) => {
                  const first = group.messages[0];
                  if (!first) return null;
                  const assistant =
                    group.isGroup ||
                    first.role === "assistant" ||
                    first.role === "tool";
                  const label = turnLabel(group);
                  return (
                    <section key={first.id} className={styles.turn}>
                      {label ? (
                        <div
                          className={
                            first.role === "user"
                              ? `${styles.speaker} ${styles.speakerUser}`
                              : styles.speaker
                          }
                        >
                          {label}
                        </div>
                      ) : null}
                      {assistant ? (
                        <AssistantTurnView
                          messages={group.messages}
                          readAloud={false}
                        />
                      ) : (
                        <MessageBubble message={first} readAloud={false} />
                      )}
                    </section>
                  );
                })}
              </div>
            )}
            <p className={styles.footer}>{t("chat.sharePage.footer")}</p>
            <div className={styles.state}>
              <Button onClick={() => void load()}>
                {t("chat.sharePage.refresh")}
              </Button>
            </div>
          </VoiceOutputProvider>
        ) : null}
      </div>
    </div>
  );
}
