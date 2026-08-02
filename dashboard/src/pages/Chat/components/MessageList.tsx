import {
  forwardRef,
  useEffect,
  useRef,
  useCallback,
  useMemo,
  useState,
  useLayoutEffect,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { Spin, Button } from "antd";
import { Virtuoso, type Components, type VirtuosoHandle } from "react-virtuoso";
import { useTranslation } from "react-i18next";
import type { ChatMessage } from "../hooks/useChat";
import type { ComposerTagLookups } from "./UserMessageComposerTags";
import MessageBubble from "./MessageBubble";
import AssistantTurnView from "./AssistantTurnView";
import ScrollToBottomButton from "./ScrollToBottomButton";
import GeneratingIndicator from "./GeneratingIndicator";
import { isLiveAssistantTurn } from "./liveAssistantTurn";
import { chatGeneratingPhase } from "./generatingGate";
import { useAutoScroll } from "../hooks/useAutoScroll";
import { findLastBrowserTurnGroupIndex } from "../utils/messageContent";
import {
  groupConsecutiveAssistantMessages,
  type MessageGroup,
} from "../utils/messageGrouping";
import {
  nextCanLoadOlder,
  shouldAutoFillOlderHistory,
  shouldReleaseLoadMoreLatch,
} from "./loadOlderGate";
import styles from "../index.module.less";

/** Virtualize long threads; short chats keep the simpler DOM path. */
const VIRTUALIZE_THRESHOLD = 30;

/** Virtuoso prepend anchor — count down when older pages are prepended. */
const VIRTUOSO_START_INDEX = 1_000_000;

interface VirtuosoListContext {
  historyHeader: ReactNode;
  footer: ReactNode;
}

type VirtuosoListProps = HTMLAttributes<HTMLDivElement> & {
  context?: VirtuosoListContext;
};

const VirtuosoList = forwardRef<HTMLDivElement, VirtuosoListProps>(
  function VirtuosoList(
    { style, children, className, context: _context, ...props },
    ref,
  ) {
    return (
      <div
        ref={ref}
        {...props}
        style={style}
        className={[styles.messageListInner, className]
          .filter(Boolean)
          .join(" ")}
      >
        {children}
      </div>
    );
  },
);

/** Stable identity — avoid remounting Header/Footer on every parent render. */
const virtuosoComponents: Components<MessageGroup, VirtuosoListContext> = {
  List: VirtuosoList as Components<MessageGroup, VirtuosoListContext>["List"],
  Header: ({ context }) =>
    context?.historyHeader ? <div>{context.historyHeader}</div> : null,
  Footer: ({ context }) =>
    context?.footer ? <div>{context.footer}</div> : null,
};

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
  lastUserGroupIndex: number;
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
  const isTurnInProgress = isLiveAssistantTurn({
    isStreaming: Boolean(ctx.isStreaming),
    groupIndex,
    lastAssistantGroupIndex: ctx.lastAssistantGroupIndex,
    lastUserGroupIndex: ctx.lastUserGroupIndex,
  });

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

  const groupKey = group.messages[0]?.id ?? "assistant-turn";
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
  /** Virtuoso reports at-top separately — scrollTop is not near 0 with firstItemIndex. */
  const atTopRef = useRef(false);
  const lastSmoothScrolledUserIdRef = useRef<string | null>(null);
  const skipNextDepsScrollRef = useRef(false);
  const [scrollerMountKey, setScrollerMountKey] = useState(0);
  const [useVirtualLocked, setUseVirtualLocked] = useState(false);
  const [firstItemIndex, setFirstItemIndex] = useState(VIRTUOSO_START_INDEX);
  const prevGroupCountRef = useRef(0);

  const messageGroups = useMemo(
    () => groupConsecutiveAssistantMessages(messages),
    [messages],
  );

  const useVirtual =
    useVirtualLocked || messageGroups.length >= VIRTUALIZE_THRESHOLD;

  const lastMsg = messages[messages.length - 1];
  const { showFooter: showGenerating, showElapsed: isAwaitingAssistantReply } =
    chatGeneratingPhase({
      isStreaming: Boolean(isStreaming),
      loading: Boolean(loading),
      lastMessageRole: lastMsg?.role,
    });

  const stableSessionKey = sessionKey || "__default__";

  // Keep this callback identity stable. An inline parent `onLoadMoreHistory`
  // (or flag churn) used to recreate it every render → useAutoScroll re-bound
  // scroll listeners and Virtuoso Header/Footer remounted, which broke the
  // "scroll up → load earlier" gesture in practice.
  const loadOlderGateRef = useRef({
    historyHasMore,
    historyLoadingMore,
    loading,
    onLoadMoreHistory,
    useVirtual,
  });
  loadOlderGateRef.current = {
    historyHasMore,
    historyLoadingMore,
    loading,
    onLoadMoreHistory,
    useVirtual,
  };

  const requestOlderMessages = useCallback(() => {
    const g = loadOlderGateRef.current;
    if (
      !canLoadOlderRef.current ||
      !g.historyHasMore ||
      g.historyLoadingMore ||
      g.loading ||
      !g.onLoadMoreHistory ||
      loadMoreRequestedRef.current
    ) {
      return;
    }
    const scroller = g.useVirtual ? scrollerRef.current : containerRef.current;
    if (scroller instanceof HTMLElement) {
      scrollHeightBeforePrependRef.current = scroller.scrollHeight;
    }
    loadMoreRequestedRef.current = true;
    void Promise.resolve(g.onLoadMoreHistory()).then(
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
  }, []);

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

  const virtualItemCountRef = useRef(messageGroups.length);
  virtualItemCountRef.current = messageGroups.length;
  const firstItemIndexRef = useRef(firstItemIndex);
  firstItemIndexRef.current = firstItemIndex;

  const virtualScrollConfig = useMemo(
    () =>
      useVirtual
        ? {
            virtuosoRef,
            scrollerRef,
            itemCountRef: virtualItemCountRef,
            firstItemIndexRef,
          }
        : null,
    [useVirtual],
  );

  // Fingerprint the in-progress assistant turn (not only the last message).
  // Thinking often lives on an earlier bubble while tools stream on later ones;
  // tool results grow in toolData without changing `content`.
  // Generating footer height is stable for the whole stream — omit from token.
  const scrollFollowToken = useMemo(() => {
    let token = `${messages.length}|${showGenerating ? 1 : 0}`;
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "user") break;
      const blocksLen =
        m.contentBlocks?.reduce((n, b) => n + b.content.length, 0) ?? 0;
      const toolArgs = m.toolData?.arguments?.length ?? 0;
      const toolResult = m.toolData?.output?.length ?? 0;
      token += `|${m.id}:${m.status}:${m.content.length}:${blocksLen}:${toolArgs}:${toolResult}`;
    }
    return token;
  }, [messages, showGenerating]);

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
    // Virtuoso + firstItemIndex: at-top is not scrollTop≈0. Non-virtual omits
    // this so scrollTop near 0 still counts.
    ...(useVirtual ? { isAtTop: () => atTopRef.current } : {}),
    onOverscrollBottom: requestRefreshMessages,
    deps: [scrollFollowToken],
    skipNextDepsScrollRef,
  });

  const handleAtTopStateChange = useCallback(
    (atTop: boolean) => {
      atTopRef.current = atTop;
      if (atTop) requestOlderMessages();
    },
    [requestOlderMessages],
  );
  useEffect(() => {
    if (!historyLoadingMore) {
      loadMoreRequestedRef.current = false;
      // Still parked at the top after a page lands — keep loading without a click.
      if (atTopRef.current) {
        requestOlderMessages();
      }
    }
  }, [historyLoadingMore, requestOlderMessages]);

  useLayoutEffect(() => {
    const prevCount = prevGroupCountRef.current;
    const nextCount = messageGroups.length;
    const prependedGroups = nextCount - prevCount;
    prevGroupCountRef.current = nextCount;

    if (scrollHeightBeforePrependRef.current === null) return;

    // Virtuoso items are groups — shift firstItemIndex by the number of new
    // groups, not messages. Message-count deltas misalign absolute indices and
    // break startReached / scroll-up load-earlier.
    if (useVirtual && prependedGroups > 0) {
      setFirstItemIndex((idx) => idx - prependedGroups);
      scrollHeightBeforePrependRef.current = null;
      return;
    }

    // Non-virtual, or virtual with 0 new groups (older msgs merged into the
    // first assistant group): restore scroll by height delta.
    const scroller = useVirtual ? scrollerRef.current : containerRef.current;
    if (scroller instanceof HTMLElement) {
      armProgrammaticGuard();
      const delta =
        scroller.scrollHeight - scrollHeightBeforePrependRef.current;
      scroller.scrollTop += delta;
    }
    scrollHeightBeforePrependRef.current = null;
  }, [messages, messageGroups.length, useVirtual, armProgrammaticGuard]);

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
          <>
            <span className={styles.historyLoadMoreHint}>
              {t("chat.scrollForEarlierMessages")}
            </span>
            <Button
              type="link"
              size="small"
              className={styles.historyLoadMoreBtn}
              onClick={requestOlderMessages}
            >
              {t("chat.loadEarlierMessages")}
            </Button>
          </>
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

  const lastUserGroupIndex = useMemo(() => {
    for (let i = messageGroups.length - 1; i >= 0; i--) {
      if (messageGroups[i].messages.some((m) => m.role === "user")) return i;
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
    atTopRef.current = false;
    lastSmoothScrolledUserIdRef.current = null;
    scrollHeightBeforePrependRef.current = null;
    prevGroupCountRef.current = 0;
    setFirstItemIndex(VIRTUOSO_START_INDEX);
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
  // Do not gate on isStreaming: load-earlier must work during an in-flight reply.
  useEffect(() => {
    if (
      !shouldAutoFillOlderHistory({
        historyHasMore: Boolean(historyHasMore),
        historyLoadingMore: Boolean(historyLoadingMore),
        loading: Boolean(loading),
        canLoadOlder: canLoadOlderRef.current,
      })
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

  useLayoutEffect(() => {
    // First paint after history arrives: pin before the browser paints the
    // top-of-thread frame (avoids a visible top→bottom jump on refresh).
    if (messages.length === 0) return;
    if (!(prevInitialLoadingRef.current || loading)) return;
    const scroller = useVirtual ? scrollerRef.current : containerRef.current;
    if (scroller instanceof HTMLElement) {
      armProgrammaticGuard(320);
      scroller.scrollTop = scroller.scrollHeight;
    } else {
      scrollToBottomRef.current(true);
    }
    prevInitialLoadingRef.current = !!loading;
  }, [loading, messages.length, useVirtual, armProgrammaticGuard]);

  useEffect(() => {
    prevInitialLoadingRef.current = !!loading;
  }, [loading]);

  // On send: pin instantly in layout so the new user bubble is visible before
  // paint. A deferred smooth scroll left a frame where the message was below
  // the fold, then animated the list upward.
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
    scrollToBottom(true, true);
  }, [isStreaming, messages, scrollToBottom]);

  const groupContext = useMemo<GroupRenderContext>(
    () => ({
      agentId,
      composerLookups,
      isStreaming,
      lastBrowserGroupIndex,
      lastAssistantGroupIndex,
      lastUserGroupIndex,
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
      lastUserGroupIndex,
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

  const footer = useMemo(
    () => (
      <>
        {showGenerating && (
          <div className={styles.generatingSlot}>
            <GeneratingIndicator
              startedAt={thinkingStartedAt}
              showElapsed={isAwaitingAssistantReply}
              onCancel={onCancel}
            />
          </div>
        )}
        {refreshFooter}
      </>
    ),
    [
      showGenerating,
      thinkingStartedAt,
      isAwaitingAssistantReply,
      onCancel,
      refreshFooter,
    ],
  );

  const hasFooter = showGenerating || Boolean(refreshFooter);

  const virtuosoContext = useMemo<VirtuosoListContext>(
    () => ({
      historyHeader,
      footer: hasFooter ? footer : null,
    }),
    [historyHeader, hasFooter, footer],
  );

  if (loading && messages.length === 0) {
    return (
      <div className={styles.messageListLoading}>
        <Spin />
      </div>
    );
  }

  return (
    <div className={styles.messageListWrapper}>
      {useVirtual ? (
        <Virtuoso
          key={stableSessionKey}
          ref={virtuosoRef}
          className={styles.messageList}
          style={{ height: "100%" }}
          data={messageGroups}
          context={virtuosoContext}
          firstItemIndex={firstItemIndex}
          initialTopMostItemIndex={
            messageGroups.length === 0
              ? firstItemIndex
              : firstItemIndex + messageGroups.length - 1
          }
          increaseViewportBy={{ top: 600, bottom: 800 }}
          followOutput={false}
          atBottomStateChange={handleAtBottomChange}
          atTopStateChange={handleAtTopStateChange}
          atTopThreshold={200}
          startReached={requestOlderMessages}
          scrollerRef={(el) => {
            const next = el instanceof HTMLElement ? el : null;
            if (next !== scrollerRef.current) {
              scrollerRef.current = next;
              if (next) setScrollerMountKey((k) => k + 1);
            }
          }}
          components={virtuosoComponents}
          itemContent={(index, group) =>
            renderMessageGroup(group, index - firstItemIndex, groupContext)
          }
        />
      ) : (
        <div className={styles.messageList} ref={containerRef}>
          <div className={styles.messageListInner}>
            {historyHeader}
            {messageGroups.map((group, groupIndex) => (
              // Stable key: first message id only. Joining all ids remounts the
              // whole assistant turn whenever a tool/thinking bubble is appended.
              <div key={group.messages[0]?.id ?? `g-${groupIndex}`}>
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
