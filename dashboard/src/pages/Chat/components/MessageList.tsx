import {
  forwardRef,
  useEffect,
  useRef,
  useCallback,
  useMemo,
  useState,
  useLayoutEffect,
} from "react";
import { Spin, Button } from "antd";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../hooks/useChat";
import type { ComposerTagLookups } from "./UserMessageComposerTags";
import MessageBubble from "./MessageBubble";
import AssistantTurnView from "./AssistantTurnView";
import ThinkingBubble from "./ThinkingBubble";
import ScrollToBottomButton from "./ScrollToBottomButton";
import ContinuingIndicator from "./ContinuingIndicator";
import { useAutoScroll } from "../hooks/useAutoScroll";
import { findLastBrowserTurnGroupIndex } from "../utils/messageContent";
import {
  groupConsecutiveAssistantMessages,
  type MessageGroup,
} from "../utils/messageGrouping";
import { nextCanLoadOlder, shouldReleaseLoadMoreLatch } from "./loadOlderGate";
import styles from "../index.module.less";

/** Virtualize long threads; short chats keep the simpler DOM path. */
const VIRTUALIZE_THRESHOLD = 30;

const VirtuosoList = forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(function VirtuosoList({ style, children, className, ...props }, ref) {
  return (
    <div
      ref={ref}
      {...props}
      style={style}
      className={[styles.messageListInner, className].filter(Boolean).join(" ")}
    >
      {children}
    </div>
  );
});

const virtuosoComponents = { List: VirtuosoList };

interface MessageListProps {
  messages: ChatMessage[];
  agentId?: string | null;
  composerLookups?: ComposerTagLookups;
  loading?: boolean;
  historyHasMore?: boolean;
  historyLoadingMore?: boolean;
  historyRefreshing?: boolean;
  /** Return false when the load did not start (caller must release any latch). */
  onLoadMoreHistory?: () => boolean | void | Promise<boolean | void>;
  onRefreshHistory?: () => void;
  isStreaming?: boolean;
  thinkingStartedAt?: number | null;
  sessionKey?: string;
  onCancel?: () => void;
  onRegenerate?: (messageId: string) => void;
  onEditUserMessage?: (messageId: string, newText: string) => void;
  onAcpPermissionSelect?: (message: string) => void;
  onHitlDecision?: (
    decisions: Array<{ type: string; message?: string }>,
  ) => void;
  onOpenBrowser?: () => void;
  onEditFile?: () => void;
  onRunShellCommand?: (code: string) => void;
  shellCommandDisabled?: boolean;
  shellCommandDisabledTitle?: string;
  compactProcess?: boolean;
}

interface GroupRenderContext {
  agentId?: string | null;
  composerLookups?: ComposerTagLookups;
  isStreaming?: boolean;
  lastBrowserGroupIndex: number;
  lastAssistantGroupIndex: number;
  onRegenerate?: (messageId: string) => void;
  onEditUserMessage?: (messageId: string, newText: string) => void;
  onAcpPermissionSelect?: (message: string) => void;
  onHitlDecision?: (
    decisions: Array<{ type: string; message?: string }>,
  ) => void;
  onOpenBrowser?: () => void;
  onEditFile?: () => void;
  onRunShellCommand?: (code: string) => void;
  shellCommandDisabled?: boolean;
  shellCommandDisabledTitle?: string;
  compactProcess?: boolean;
  registerBubbleRef: (messageId: string, el: HTMLDivElement | null) => void;
}

function renderMessageGroup(
  group: MessageGroup,
  groupIndex: number,
  ctx: GroupRenderContext,
) {
  const openBrowserHandler =
    ctx.onOpenBrowser && groupIndex === ctx.lastBrowserGroupIndex
      ? ctx.onOpenBrowser
      : undefined;
  const isTurnInProgress =
    ctx.isStreaming && groupIndex === ctx.lastAssistantGroupIndex;

  if (!group.isGroup || group.messages.length === 1) {
    const msg = group.messages[0];
    if (msg.role === "assistant") {
      return (
        <div
          ref={(el) => {
            ctx.registerBubbleRef(msg.id, el);
          }}
        >
          <AssistantTurnView
            messages={[msg]}
            agentId={ctx.agentId}
            isStreaming={ctx.isStreaming}
            isTurnInProgress={isTurnInProgress}
            onRegenerate={ctx.onRegenerate}
            onEditUserMessage={ctx.onEditUserMessage}
            onAcpPermissionSelect={ctx.onAcpPermissionSelect}
            onHitlDecision={ctx.onHitlDecision}
            onOpenBrowser={openBrowserHandler}
            onEditFile={ctx.onEditFile}
            onRunShellCommand={ctx.onRunShellCommand}
            shellCommandDisabled={ctx.shellCommandDisabled}
            shellCommandDisabledTitle={ctx.shellCommandDisabledTitle}
            compactProcess={ctx.compactProcess}
          />
        </div>
      );
    }
    return (
      <div
        ref={(el) => {
          ctx.registerBubbleRef(msg.id, el);
        }}
      >
        <MessageBubble
          message={msg}
          agentId={ctx.agentId}
          composerLookups={ctx.composerLookups}
          onRegenerate={ctx.onRegenerate}
          onEditUserMessage={ctx.onEditUserMessage}
        />
      </div>
    );
  }

  const groupKey = group.messages.map((m) => m.id).join("|");
  return (
    <div
      key={groupKey}
      ref={(el) => {
        for (const msg of group.messages) {
          ctx.registerBubbleRef(msg.id, el);
        }
      }}
    >
      <AssistantTurnView
        messages={group.messages}
        agentId={ctx.agentId}
        isStreaming={ctx.isStreaming}
        isTurnInProgress={isTurnInProgress}
        onRegenerate={ctx.onRegenerate}
        onEditUserMessage={ctx.onEditUserMessage}
        onAcpPermissionSelect={ctx.onAcpPermissionSelect}
        onHitlDecision={ctx.onHitlDecision}
        onOpenBrowser={openBrowserHandler}
        onEditFile={ctx.onEditFile}
        onRunShellCommand={ctx.onRunShellCommand}
        shellCommandDisabled={ctx.shellCommandDisabled}
        shellCommandDisabledTitle={ctx.shellCommandDisabledTitle}
        compactProcess={ctx.compactProcess}
      />
    </div>
  );
}

export default function MessageList(props: MessageListProps) {
  const {
    messages,
    agentId,
    composerLookups,
    loading,
    historyHasMore,
    historyLoadingMore,
    historyRefreshing,
    onLoadMoreHistory,
    onRefreshHistory,
    isStreaming,
    thinkingStartedAt = null,
    sessionKey,
    onCancel,
    onRegenerate,
    onEditUserMessage,
    onAcpPermissionSelect,
    onHitlDecision,
    onOpenBrowser,
    onEditFile,
    onRunShellCommand,
    shellCommandDisabled,
    shellCommandDisabledTitle,
    compactProcess,
  } = props;

  const { t } = useTranslation();
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLElement | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const bubbleRefsMap = useRef<Map<string, HTMLDivElement>>(new Map());
  const prevInitialLoadingRef = useRef(false);
  const scrollHeightBeforePrependRef = useRef<number | null>(null);
  const loadMoreRequestedRef = useRef(false);
  const canLoadOlderRef = useRef(false);
  const lastSmoothScrolledUserIdRef = useRef<string | null>(null);
  const skipNextDepsScrollRef = useRef(false);
  const [scrollerMountKey, setScrollerMountKey] = useState(0);
  const [useVirtualLocked, setUseVirtualLocked] = useState(false);

  const messageGroups = useMemo(
    () => groupConsecutiveAssistantMessages(messages),
    [messages],
  );

  const useVirtual =
    useVirtualLocked || messageGroups.length >= VIRTUALIZE_THRESHOLD;

  const lastMsg = messages[messages.length - 1];
  const isAwaitingAssistantReply = Boolean(
    isStreaming && (!lastMsg || lastMsg.role === "user"),
  );
  const showThinking = Boolean(!loading && isAwaitingAssistantReply);
  const showContinuing =
    isStreaming &&
    !showThinking &&
    lastMsg?.role === "assistant" &&
    lastMsg.status === "done";

  const stableSessionKey = sessionKey || "__default__";

  const requestOlderMessages = useCallback(() => {
    if (
      !canLoadOlderRef.current ||
      !historyHasMore ||
      historyLoadingMore ||
      loading ||
      isStreaming ||
      !onLoadMoreHistory ||
      loadMoreRequestedRef.current
    ) {
      return;
    }
    const scroller = useVirtual ? scrollerRef.current : containerRef.current;
    if (scroller instanceof HTMLElement) {
      scrollHeightBeforePrependRef.current = scroller.scrollHeight;
    }
    loadMoreRequestedRef.current = true;
    void Promise.resolve(onLoadMoreHistory()).then(
      (started) => {
        // Early-return in loadMoreHistory leaves historyLoadingMore false, so the
        // effect below never clears this latch — release it explicitly.
        if (shouldReleaseLoadMoreLatch(started)) {
          loadMoreRequestedRef.current = false;
          scrollHeightBeforePrependRef.current = null;
        }
      },
      () => {
        loadMoreRequestedRef.current = false;
        scrollHeightBeforePrependRef.current = null;
      },
    );
  }, [
    historyHasMore,
    historyLoadingMore,
    loading,
    isStreaming,
    onLoadMoreHistory,
    useVirtual,
  ]);

  // Keep the refresh trigger's identity stable so the scroll-listener effect
  // in useAutoScroll never re-mounts (which would reset its overscroll guard
  // and fire the refresh twice). Latest values are read from a ref.
  const refreshStateRef = useRef({
    historyRefreshing,
    loading,
    isStreaming,
    onRefreshHistory,
    hasMessages: messages.length > 0,
  });
  refreshStateRef.current = {
    historyRefreshing,
    loading,
    isStreaming,
    onRefreshHistory,
    hasMessages: messages.length > 0,
  };
  const refreshCooldownRef = useRef(0);

  const requestRefreshMessages = useCallback(() => {
    const s = refreshStateRef.current;
    const now = Date.now();
    if (
      s.historyRefreshing ||
      s.loading ||
      s.isStreaming ||
      !s.onRefreshHistory ||
      !s.hasMessages ||
      now - refreshCooldownRef.current < 3000
    ) {
      return;
    }
    refreshCooldownRef.current = now;
    s.onRefreshHistory();
  }, []);

  const virtualScrollConfig = useMemo(
    () =>
      useVirtual
        ? {
            virtuosoRef,
            scrollerRef,
            itemCount: messageGroups.length,
          }
        : null,
    [useVirtual, messageGroups.length],
  );

  const scrollFollowDeps = useMemo(
    () => ({
      count: messages.length,
      lastId: lastMsg?.id ?? "",
      lastContent: lastMsg?.content ?? "",
      lastStatus: lastMsg?.status ?? "",
      showThinking,
      showContinuing,
    }),
    [messages.length, lastMsg, showThinking, showContinuing],
  );

  const {
    showScrollBtn,
    scrollToBottom,
    armProgrammaticGuard,
    handleAtBottomChange,
  } = useAutoScroll({
    containerRef,
    endRef,
    virtual: virtualScrollConfig,
    scrollerMountKey,
    onNearTop: requestOlderMessages,
    onOverscrollBottom: requestRefreshMessages,
    deps: [
      scrollFollowDeps.count,
      scrollFollowDeps.lastId,
      scrollFollowDeps.lastContent,
      scrollFollowDeps.lastStatus,
      scrollFollowDeps.showThinking,
      scrollFollowDeps.showContinuing,
    ],
    skipNextDepsScrollRef,
  });

  useEffect(() => {
    if (!historyLoadingMore) {
      loadMoreRequestedRef.current = false;
    }
  }, [historyLoadingMore]);

  useLayoutEffect(() => {
    if (scrollHeightBeforePrependRef.current === null) return;
    const scroller = useVirtual ? scrollerRef.current : containerRef.current;
    if (scroller instanceof HTMLElement) {
      armProgrammaticGuard();
      const delta =
        scroller.scrollHeight - scrollHeightBeforePrependRef.current;
      scroller.scrollTop += delta;
    }
    scrollHeightBeforePrependRef.current = null;
  }, [messages, useVirtual, armProgrammaticGuard]);

  const historyHeader = useMemo(() => {
    if (!historyHasMore && !historyLoadingMore) return null;
    return (
      <div className={styles.historyLoadMore}>
        {historyLoadingMore ? (
          <>
            <Spin size="small" />
            <span>{t("chat.loadingEarlierMessages")}</span>
          </>
        ) : (
          <Button
            type="link"
            size="small"
            className={styles.historyLoadMoreBtn}
            onClick={requestOlderMessages}
          >
            {t("chat.loadEarlierMessages")}
          </Button>
        )}
      </div>
    );
  }, [historyHasMore, historyLoadingMore, requestOlderMessages, t]);

  const refreshFooter = useMemo(() => {
    if (!historyRefreshing) return null;
    return (
      <div className={styles.historyLoadMore}>
        <Spin size="small" />
        <span>{t("chat.refreshingMessages")}</span>
      </div>
    );
  }, [historyRefreshing, t]);

  const lastBrowserGroupIndex = useMemo(
    () => findLastBrowserTurnGroupIndex(messageGroups),
    [messageGroups],
  );

  const lastAssistantGroupIndex = useMemo(() => {
    for (let i = messageGroups.length - 1; i >= 0; i--) {
      if (messageGroups[i].messages.some((m) => m.role === "assistant"))
        return i;
    }
    return -1;
  }, [messageGroups]);

  const registerBubbleRef = useCallback(
    (messageId: string, el: HTMLDivElement | null) => {
      if (el) bubbleRefsMap.current.set(messageId, el);
      else bubbleRefsMap.current.delete(messageId);
    },
    [],
  );

  // Keep scrollToBottom identity out of session-reset deps: virtual itemCount
  // changes every message and would re-disarm canLoadOlder permanently.
  const scrollToBottomRef = useRef(scrollToBottom);
  scrollToBottomRef.current = scrollToBottom;

  useEffect(() => {
    setUseVirtualLocked(false);
    loadMoreRequestedRef.current = false;
    canLoadOlderRef.current = nextCanLoadOlder({
      kind: "session-reset",
      loading: !!loading,
      messageCount: messages.length,
    });
    lastSmoothScrolledUserIdRef.current = null;
    scrollHeightBeforePrependRef.current = null;
    scrollToBottomRef.current(true);
    // Intentionally only sessionKey — see scrollToBottomRef above.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- session switch only
  }, [stableSessionKey]);

  // Re-arm after session reset (must run after the effect above).
  useEffect(() => {
    if (
      nextCanLoadOlder({
        kind: "history-ready",
        loading: !!loading,
        messageCount: messages.length,
      })
    ) {
      canLoadOlderRef.current = true;
    }
  }, [loading, messages.length, stableSessionKey]);

  // When the list does not overflow, scroll-to-top never fires — keep loading
  // older pages until content can scroll or the server says there is no more.
  useEffect(() => {
    if (
      !historyHasMore ||
      historyLoadingMore ||
      loading ||
      isStreaming ||
      !canLoadOlderRef.current
    ) {
      return;
    }
    const scroller = useVirtual ? scrollerRef.current : containerRef.current;
    if (!(scroller instanceof HTMLElement)) return;
    if (scroller.scrollHeight <= scroller.clientHeight + 80) {
      requestOlderMessages();
    }
  }, [
    historyHasMore,
    historyLoadingMore,
    loading,
    isStreaming,
    messages.length,
    useVirtual,
    scrollerMountKey,
    requestOlderMessages,
  ]);

  useEffect(() => {
    if (messageGroups.length >= VIRTUALIZE_THRESHOLD) {
      setUseVirtualLocked(true);
    }
  }, [messageGroups.length]);

  useEffect(() => {
    if (prevInitialLoadingRef.current && !loading && messages.length > 0) {
      scrollToBottomRef.current(true);
    }
    prevInitialLoadingRef.current = !!loading;
  }, [loading, messages.length]);

  useLayoutEffect(() => {
    if (!isStreaming) {
      lastSmoothScrolledUserIdRef.current = null;
      return;
    }

    const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUserMsg) return;
    if (lastSmoothScrolledUserIdRef.current === lastUserMsg.id) return;
    lastSmoothScrolledUserIdRef.current = lastUserMsg.id;

    skipNextDepsScrollRef.current = true;
    scrollToBottom(false);
  }, [isStreaming, messages, scrollToBottom]);

  const groupContext = useMemo<GroupRenderContext>(
    () => ({
      agentId,
      composerLookups,
      isStreaming,
      lastBrowserGroupIndex,
      lastAssistantGroupIndex,
      onRegenerate,
      onEditUserMessage,
      onAcpPermissionSelect,
      onHitlDecision,
      onOpenBrowser,
      onEditFile,
      onRunShellCommand,
      shellCommandDisabled,
      shellCommandDisabledTitle,
      compactProcess,
      registerBubbleRef,
    }),
    [
      agentId,
      composerLookups,
      isStreaming,
      lastBrowserGroupIndex,
      lastAssistantGroupIndex,
      onRegenerate,
      onEditUserMessage,
      onAcpPermissionSelect,
      onHitlDecision,
      onOpenBrowser,
      onEditFile,
      onRunShellCommand,
      shellCommandDisabled,
      shellCommandDisabledTitle,
      compactProcess,
      registerBubbleRef,
    ],
  );

  if (loading) {
    return (
      <div className={styles.messageListLoading}>
        <Spin />
      </div>
    );
  }

  const footer = (
    <>
      {showThinking && thinkingStartedAt != null && (
        <ThinkingBubble startedAt={thinkingStartedAt} onCancel={onCancel} />
      )}
      {showContinuing && <ContinuingIndicator onCancel={onCancel} />}
      {refreshFooter}
    </>
  );

  return (
    <div className={styles.messageListWrapper}>
      {useVirtual ? (
        <Virtuoso
          key={stableSessionKey}
          ref={virtuosoRef}
          className={styles.messageList}
          style={{ height: "100%" }}
          data={messageGroups}
          initialTopMostItemIndex={Math.max(0, messageGroups.length - 1)}
          increaseViewportBy={{ top: 600, bottom: 800 }}
          followOutput={false}
          atBottomStateChange={handleAtBottomChange}
          atTopThreshold={200}
          startReached={requestOlderMessages}
          scrollerRef={(el) => {
            const next = el instanceof HTMLElement ? el : null;
            if (next !== scrollerRef.current) {
              scrollerRef.current = next;
              if (next) setScrollerMountKey((k) => k + 1);
            }
          }}
          components={{
            ...virtuosoComponents,
            Header: () => (historyHeader ? <div>{historyHeader}</div> : null),
            Footer: () =>
              showThinking || showContinuing || refreshFooter ? (
                <div>{footer}</div>
              ) : null,
          }}
          itemContent={(index, group) =>
            renderMessageGroup(group, index, groupContext)
          }
        />
      ) : (
        <div className={styles.messageList} ref={containerRef}>
          <div className={styles.messageListInner}>
            {historyHeader}
            {messageGroups.map((group, groupIndex) => (
              <div key={group.messages.map((m) => m.id).join("|")}>
                {renderMessageGroup(group, groupIndex, groupContext)}
              </div>
            ))}
            {footer}
            <div ref={endRef} style={{ height: 1 }} aria-hidden="true" />
          </div>
        </div>
      )}

      <ScrollToBottomButton
        visible={showScrollBtn}
        onClick={() => scrollToBottom()}
      />
    </div>
  );
}
