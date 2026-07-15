import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { PanelLeftOpen, GraduationCap } from "lucide-react";
import { Tooltip } from "antd";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useChat } from "./hooks/useChat";
import { useSessions } from "./hooks/useSessions";
import * as chatStore from "./hooks/chatStore";
import { formatRunUsage } from "./utils/chatMessages";
import { useChatSidebarState } from "./hooks/useChatSidebarState";
import { useChatBrowserPanel } from "./hooks/useChatBrowserPanel";
import { useChatSend } from "./hooks/useChatSend";
import { useChatNavigation } from "./hooks/useChatNavigation";
import { useChatSessionActions } from "./hooks/useChatSessionActions";

import { useChatComposerResources } from "./hooks/useChatComposerResources";
import { useChatContextWindow } from "./hooks/useChatContextWindow";
import { useBrowserToolDetection } from "./hooks/useBrowserToolDetection";
import { useSkillRecordingWorkflow } from "./hooks/useSkillRecordingWorkflow";
import { browserApi } from "../../api/modules/browser";
import type { TokenUsage } from "../../api/types";
import type { ChatAttachment } from "./hooks/useChat";
import MessageList from "./components/MessageList";
import ChatInput, { type ChatInputHandle } from "./components/ChatInput";
import WelcomeScreen from "./components/WelcomeScreen";
import AgentNotReadyScreen from "./components/AgentNotReadyScreen";
import AgentProfileDrawer from "../../components/AgentProfileDrawer";
import { useExpertChatWelcome } from "./hooks/useExpertQuickCards";
import { useSkills } from "../Agent/Skills/useSkills";
import { useAgent } from "../../context/AgentContext";
import { useBrowserSessionState } from "../../hooks/useBrowserSessionState";
import { prefetchVoiceConfig } from "../../hooks/useVoiceConfig";
import ChatBrowserPanels from "./components/ChatBrowserPanels";
import ChatBrowserBottomPanel from "./components/ChatBrowserBottomPanel";
import ChatSidebarPanel from "./components/ChatSidebarPanel";
import ChatComposerChrome from "./components/ChatComposerChrome";
import { isAgentChatReady } from "../../utils/agentError";
import styles from "./index.module.less";

export default function ChatPage() {
  return <ChatPageInner />;
}

function ChatPageInner() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  prefetchVoiceConfig();
  const { agentId: routeAgentId, threadId } = useParams<{
    agentId?: string;
    threadId?: string;
  }>();
  const isMobile = useIsMobile();
  const [selectedTargetAgents, setSelectedTargetAgents] = useState<string[]>(
    [],
  );
  const [browserRecording, setBrowserRecording] = useState(false);
  const [browserRecordingId, setBrowserRecordingId] = useState<string | null>(
    null,
  );
  const [, setBrowserLastRecordingId] = useState<string | null>(null);
  const {
    sidebarOpen,
    setSidebarOpen,
    sidebarWidth,
    handleSidebarResizeStart,
  } = useChatSidebarState(isMobile);

  // Pre-fill text from router state or module-level pending prefill
  // (set by cron-jobs suggestions before navigating here).
  // Stored as a ref (not state) so it never triggers a parent re-render —
  // re-renders would cause ChatInput to receive a new initialText prop and
  // potentially overwrite text the user is already editing.
  const prefillInputRef = useRef(
    chatStore.consumePendingPrefillText() ||
      ((location.state as { prefillInput?: string } | null)?.prefillInput ??
        ""),
  );
  // Imperative handle to push a new prefill into the already-mounted ChatInput.
  const chatInputRef = useRef<ChatInputHandle | null>(null);

  // Clear the router state after consuming prefillInput so it doesn't persist
  // on subsequent visits or page refreshes.
  useEffect(() => {
    if (prefillInputRef.current) {
      navigate(location.pathname, { replace: true, state: {} });
    }
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When location.state arrives with a new prefillInput (component already mounted,
  // user navigated here again from another page), push it imperatively so we
  // never trigger a parent re-render that could disrupt the user's editing.
  useEffect(() => {
    const pending = chatStore.consumePendingPrefillText();
    const val =
      pending ||
      ((location.state as { prefillInput?: string } | null)?.prefillInput ??
        "");
    if (val && val !== prefillInputRef.current) {
      prefillInputRef.current = val;
      chatInputRef.current?.setPrefillText(val);
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location.state, location.pathname, navigate]);

  const activeThreadId = threadId || null;

  const {
    activeAgentId,
    agents,
    setActiveAgent,
    refresh: refreshAgents,
    loading: agentsLoading,
  } = useAgent();
  const resolvedAgentId = routeAgentId || activeAgentId;
  const activeAgent = useMemo(
    () => agents.find((a) => a.agent_id === resolvedAgentId) ?? null,
    [agents, resolvedAgentId],
  );
  const agentChatReady = isAgentChatReady(activeAgent?.state);
  const noAgents = !agentsLoading && agents.length === 0;

  useEffect(() => {
    void refreshAgents({ silent: true });
  }, [refreshAgents]);

  const { quickCards: expertQuickCards, welcomeSuffix } =
    useExpertChatWelcome(activeAgent);
  const { skills: chatSkills } = useSkills(
    agentChatReady && !agentsLoading ? resolvedAgentId ?? null : null,
  );
  const [agentProfileOpen, setAgentProfileOpen] = useState(false);

  const {
    sessions,
    loading: sessionsLoading,
    hasMore: sessionsHasMore,
    loadingMore: sessionsLoadingMore,
    createSession,
    deleteSession,
    renameSession,
    pinSession,
    fetchSessions,
    loadMoreSessions,
    fetchAllSessions,
    ensureThreadInList,
  } = useSessions(resolvedAgentId ?? null);

  const handleLoadMoreSessions = useCallback(() => {
    void loadMoreSessions(activeThreadId ?? undefined);
  }, [loadMoreSessions, activeThreadId]);

  const handleFetchAllSessions = useCallback(() => {
    void fetchAllSessions(activeThreadId ?? undefined);
  }, [fetchAllSessions, activeThreadId]);

  useEffect(() => {
    if (routeAgentId && routeAgentId !== activeAgentId) {
      setActiveAgent(routeAgentId);
    }
  }, [routeAgentId, activeAgentId, setActiveAgent]);

  const {
    messages,
    isStreaming,
    thinkingStartedAt,
    historyLoading,
    historyHasMore,
    historyLoadingMore,
    contextUsage,
    sendMessage,
    editAndResend,
    cancelStream,
    loadHistory,
    loadMoreHistory,
    clearMessages,
    resumeHitl,
  } = useChat(activeThreadId, resolvedAgentId);

  const refreshBrowserRef = useRef<() => void>(() => {});

  const { hasBrowserTool, setHasBrowserTool } = useBrowserToolDetection(
    activeThreadId,
    messages,
    () => refreshBrowserRef.current(),
  );

  const {
    sessionId: browserSessionId,
    state: browserSessionState,
    controlOwner: browserControlOwner,
    environment: browserEnvironment,
    refresh: refreshBrowserSession,
  } = useBrowserSessionState(threadId, hasBrowserTool);

  refreshBrowserRef.current = refreshBrowserSession;

  const {
    browserPanelOpen,
    browserPanelMode,
    setBrowserPanelMode,
    panelSizes,
    isResizing,
    handleResizeStart,
    handleBrowserClose,
    toggleBrowserPanel,
    openBrowserPanel,
    resetDismissOnSessionGone,
  } = useChatBrowserPanel(isMobile);

  const prevBrowserStateRef = useRef<string>("idle");
  useEffect(() => {
    if (isMobile) return;
    prevBrowserStateRef.current = browserSessionState;
    resetDismissOnSessionGone(browserSessionId);
  }, [
    browserSessionId,
    browserSessionState,
    isMobile,
    resetDismissOnSessionGone,
  ]);

  const {
    selectedModel,
    setSelectedModel,
    selectedConnectors,
    selectedSkills,
    chatConnectors,
    availableModels,
    handleConnectorsChange,
    handleSkillsChange,
  } = useChatComposerResources(
    resolvedAgentId,
    chatSkills,
    activeAgent?.default_model,
  );

  const { contextMaxTokens, contextUsedTokens } = useChatContextWindow(
    messages,
    contextUsage,
    selectedModel,
    availableModels,
    activeAgent?.default_model,
  );

  const sessionUsage = useMemo(() => {
    const acc: TokenUsage = {};
    for (const msg of messages) {
      const u = msg.usage;
      if (!u) continue;
      if (typeof u.input_tokens === "number") {
        acc.input_tokens = (acc.input_tokens || 0) + u.input_tokens;
      }
      if (typeof u.output_tokens === "number") {
        acc.output_tokens = (acc.output_tokens || 0) + u.output_tokens;
      }
      if (typeof u.total_tokens === "number") {
        acc.total_tokens = (acc.total_tokens || 0) + u.total_tokens;
      }
    }
    if (!acc.input_tokens && !acc.output_tokens && !acc.total_tokens) {
      return null;
    }
    return acc;
  }, [messages]);
  const sessionUsageLabel = formatRunUsage(sessionUsage, {
    input: t("chatUsage.input"),
    output: t("chatUsage.output"),
    total: t("chatUsage.total"),
  });

  const { resetNavForAgentSwitch, markInitialNavDone } = useChatNavigation({
    routeAgentId,
    threadId,
    resolvedAgentId,
    activeThreadId,
    sessions,
    sessionsLoading,
    prefillInputRef,
    loadHistory,
    clearMessages,
    ensureThreadInList,
    fetchSessions,
    refreshAgents,
  });

  const chatAgentOptions = useMemo(
    () =>
      agents.map((a) => ({
        agent_id: a.agent_id,
        name: a.name,
        icon_name: a.icon_name,
        color: a.color,
      })),
    [agents],
  );

  const composerLookups = useMemo(
    () => ({
      skills: chatSkills,
      connectors: chatConnectors,
      agents: chatAgentOptions,
    }),
    [chatSkills, chatConnectors, chatAgentOptions],
  );

  const { handleSend } = useChatSend({
    resolvedAgentId,
    activeThreadId,
    sessions,
    messagesLength: messages.length,
    selectedModel,
    selectedConnectors,
    selectedSkills,
    selectedTargetAgents,
    defaultModel: activeAgent?.default_model ?? null,
    sendMessage,
    createSession,
    renameSession,
    onAutoRecordingStarted: useCallback((recordingId: string) => {
      setBrowserRecording(true);
      setBrowserRecordingId(recordingId);
      setBrowserLastRecordingId(recordingId);
    }, []),
    t,
  });

  // --- Skill recording workflow ---
  const { interceptUserMessage } = useSkillRecordingWorkflow({
    agentId: resolvedAgentId,
    threadId: activeThreadId,
    browserRecording,
    browserRecordingId,
    setBrowserRecording,
    setBrowserRecordingId,
    setBrowserLastRecordingId,
  });

  // Wrap handleSend to intercept skill recording workflow keywords
  const wrappedHandleSend = useCallback(
    (text: string, attachments?: ChatAttachment[]) => {
      if (interceptUserMessage(text)) {
        // The workflow intercepted the message — don't send it to the agent
        return;
      }
      handleSend(text, attachments);
    },
    [interceptUserMessage, handleSend],
  );

  const {
    handleNewChat,
    handleSelectSession,
    navigateToAgent,
    handleDeleteSession,
  } = useChatSessionActions({
    resolvedAgentId,
    activeThreadId,
    sessions,
    isMobile,
    setActiveAgent,
    setSidebarOpen,
    setSelectedModel,
    setHasBrowserTool,
    deleteSession,
    clearMessages,
    resetNavForAgentSwitch,
    markInitialNavDone,
  });

  useEffect(() => {
    return chatStore.onSlashAction((ev) => {
      if (ev.action === "switch_agent" && ev.agent_id) {
        navigateToAgent(ev.agent_id);
      }
    });
  }, [navigateToAgent]);

  const handlePromptClick = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      wrappedHandleSend(trimmed);
    },
    [wrappedHandleSend],
  );

  const handleAcpPermissionSelect = useCallback(
    (permissionMessage: string) => {
      wrappedHandleSend(permissionMessage);
    },
    [wrappedHandleSend],
  );

  const handleHitlDecision = useCallback(
    (decisions: Array<{ type: string; message?: string }>) => {
      resumeHitl(decisions, activeThreadId ?? undefined);
    },
    [resumeHitl, activeThreadId],
  );

  useEffect(() => {
    let cancelled = false;
    browserApi
      .recordReplayStatus()
      .then((status) => {
        if (cancelled) return;
        setBrowserRecording(Boolean(status.active));
        setBrowserRecordingId(status.active?.recordingId ?? null);
        if (status.latestRecordingId) {
          setBrowserLastRecordingId(status.latestRecordingId);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Regenerate: re-send the last user message before this assistant message
  const handleRegenerate = useCallback(
    (messageId: string) => {
      const idx = messages.findIndex((m) => m.id === messageId);
      if (idx < 0) return;
      // Find the user message that preceded this assistant response
      let userMsg: (typeof messages)[0] | undefined;
      for (let i = idx - 1; i >= 0; i--) {
        if (messages[i].role === "user") {
          userMsg = messages[i];
          break;
        }
      }
      if (!userMsg) return;
      wrappedHandleSend(userMsg.content, userMsg.attachments);
    },
    [messages, wrappedHandleSend],
  );

  // Edit user message: truncate history from that message onwards, replace
  // its content, and re-send — mirrors Claude / ChatGPT "edit message" behaviour.
  const handleEditUserMessage = useCallback(
    (messageId: string, newText: string) => {
      if (!activeThreadId) return;
      editAndResend(messageId, newText, "", resolvedAgentId ?? "");
    },
    [activeThreadId, editAndResend, resolvedAgentId],
  );

  const hasMessages = messages.length > 0;

  return (
    <>
      <div className={styles.chatPage}>
        <ChatSidebarPanel
          isMobile={isMobile}
          sidebarOpen={sidebarOpen}
          sidebarWidth={sidebarWidth}
          agents={agents}
          sessions={sessions}
          activeThreadId={activeThreadId}
          resolvedAgentId={resolvedAgentId}
          sessionsHasMore={sessionsHasMore}
          sessionsLoadingMore={sessionsLoadingMore}
          onLoadMoreSessions={handleLoadMoreSessions}
          onFetchAllSessions={handleFetchAllSessions}
          onSelectSession={(sessionId, agentId) => {
            setActiveAgent(agentId);
            handleSelectSession(sessionId);
          }}
          onAgentSelect={navigateToAgent}
          onDeleteSession={handleDeleteSession}
          onRenameSession={renameSession}
          onPinSession={pinSession}
          onSidebarOpenChange={setSidebarOpen}
          onSidebarResizeStart={handleSidebarResizeStart}
        />

        {/* Main chat area */}
        <div
          className={`${styles.chatMain} ${
            hasBrowserTool &&
            !isMobile &&
            browserPanelOpen &&
            browserPanelMode === "bottom"
              ? styles.chatMainWithBottomPanel
              : ""
          }`}
        >
          {/* Mobile toolbar — quick actions; global Header handles logo / health / theme */}
          {isMobile && (
            <div className={styles.mobileToolbar}>
              <button
                className={styles.menuBtn}
                onClick={() => setSidebarOpen(!sidebarOpen)}
                title={t("nav.chatHistory") || "会话列表"}
              >
                <PanelLeftOpen size={18} strokeWidth={1.8} />
              </button>
              {resolvedAgentId && (
                <div className={styles.mobileToolbarRight}>
                  <button
                    className={styles.menuBtn}
                    onClick={() => setAgentProfileOpen(true)}
                    title={t("chat.agentProfile.open")}
                    aria-label={t("chat.agentProfile.open")}
                  >
                    <GraduationCap size={18} strokeWidth={1.8} />
                  </button>
                </div>
              )}
            </div>
          )}

          <div className={styles.chatContent}>
            {!agentChatReady || noAgents ? (
              <AgentNotReadyScreen
                agent={activeAgent}
                noAgents={noAgents}
                loading={agentsLoading}
              />
            ) : !hasMessages && !historyLoading ? (
              <WelcomeScreen
                agentName={activeAgent?.name ?? null}
                welcomeSuffix={welcomeSuffix}
                quickCards={expertQuickCards}
                onPromptClick={handlePromptClick}
                hideMascot={isStreaming}
              />
            ) : (
              <MessageList
                messages={messages}
                composerLookups={composerLookups}
                loading={historyLoading}
                historyHasMore={historyHasMore}
                historyLoadingMore={historyLoadingMore}
                onLoadMoreHistory={() => void loadMoreHistory()}
                isStreaming={isStreaming}
                thinkingStartedAt={thinkingStartedAt}
                sessionKey={activeThreadId ?? undefined}
                onCancel={cancelStream}
                onRegenerate={handleRegenerate}
                onEditUserMessage={handleEditUserMessage}
                onAcpPermissionSelect={handleAcpPermissionSelect}
                onHitlDecision={handleHitlDecision}
                onOpenBrowser={
                  hasBrowserTool && !isMobile ? openBrowserPanel : undefined
                }
              />
            )}
          </div>

          {resolvedAgentId && !isMobile && (
            <Tooltip title={t("chat.agentProfile.open")} mouseEnterDelay={0.35}>
              <span className={styles.agentProfileBtnWrap}>
                <button
                  type="button"
                  className={styles.agentProfileBtn}
                  onClick={() => setAgentProfileOpen(true)}
                  aria-label={t("chat.agentProfile.open")}
                >
                  <GraduationCap size={16} strokeWidth={2.25} />
                </button>
              </span>
            </Tooltip>
          )}

          <ChatComposerChrome sessionUsageLabel={sessionUsageLabel} />
          <ChatInput
            ref={chatInputRef}
            onSend={wrappedHandleSend}
            onCancel={cancelStream}
            onNewChat={handleNewChat}
            isStreaming={isStreaming}
            disabled={!agentChatReady || noAgents}
            initialText={prefillInputRef.current}
            availableModels={availableModels}
            selectedModel={selectedModel}
            onModelChange={setSelectedModel}
            availableConnectors={chatConnectors}
            selectedConnectors={selectedConnectors}
            onConnectorsChange={handleConnectorsChange}
            availableSkills={chatSkills}
            selectedSkills={selectedSkills}
            onSkillsChange={handleSkillsChange}
            availableAgents={chatAgentOptions}
            selectedTargetAgents={selectedTargetAgents}
            onTargetAgentsChange={setSelectedTargetAgents}
            agentId={resolvedAgentId}
            threadId={activeThreadId}
            defaultModel={activeAgent?.default_model ?? null}
            contextUsedTokens={contextUsedTokens}
            contextMaxTokens={contextMaxTokens}
          />

          {/* Browser Workspace — bottom panel mode (inside chatMain, desktop only) */}
          {hasBrowserTool &&
            !isMobile &&
            browserPanelOpen &&
            browserPanelMode === "bottom" && (
              <ChatBrowserBottomPanel
                sessionId={browserSessionId ?? activeThreadId ?? null}
                environment={browserEnvironment}
                isResizing={isResizing}
                bottomHeight={panelSizes.bottomHeight}
                onModeChange={setBrowserPanelMode}
                onClose={handleBrowserClose}
                onResizeStart={handleResizeStart}
              />
            )}
        </div>

        <ChatBrowserPanels
          hasBrowserTool={hasBrowserTool}
          isMobile={isMobile}
          browserPanelOpen={browserPanelOpen}
          browserPanelMode={browserPanelMode}
          isResizing={isResizing}
          panelSizes={panelSizes}
          browserSessionId={browserSessionId}
          activeThreadId={activeThreadId}
          browserEnvironment={browserEnvironment}
          browserSessionState={browserSessionState}
          browserControlOwner={browserControlOwner}
          onModeChange={setBrowserPanelMode}
          onClose={handleBrowserClose}
          onResizeStart={handleResizeStart}
          onTogglePanel={toggleBrowserPanel}
        />

        <AgentProfileDrawer
          open={agentProfileOpen}
          agent={activeAgent}
          isMobile={isMobile}
          onClose={() => setAgentProfileOpen(false)}
        />
      </div>
    </>
  );
}
