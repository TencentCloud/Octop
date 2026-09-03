import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import {
  PanelLeftOpen,
  GraduationCap,
  Globe,
  FilePen,
  Terminal,
  FolderOpen,
} from "lucide-react";
import { Tooltip } from "antd";
import { message as antMessage } from "@/utils/antdMessage";
import { showConfirmModal } from "../../utils/confirmModal";

import { useIsMobile } from "../../hooks/useIsMobile";
import { useCurrentUser } from "../../hooks/useCurrentUser";
import { userCan } from "../../utils/permissions";
import { useChat } from "./hooks/useChat";
import { useSessions, fetchAndSyncSessionArtifacts } from "./hooks/useSessions";
import * as chatStore from "./hooks/chatStore";
import { formatRunUsage, assistantTurnsFromEnd } from "./utils/chatMessages";
import { useChatSidebarState } from "./hooks/useChatSidebarState";
import { useChatHistoryRail } from "./hooks/useChatHistoryRail";
import { useChatDockPanel } from "./hooks/useChatDockPanel";
import { useChatSend, type ChatSendOverrides } from "./hooks/useChatSend";
import {
  useChatMessageQueue,
  type ChatQueueFlushContext,
  type QueuedChatItem,
} from "./hooks/useChatMessageQueue";
import { useChatNavigation } from "./hooks/useChatNavigation";
import { useChatSessionActions } from "./hooks/useChatSessionActions";

import { useChatComposerResources } from "./hooks/useChatComposerResources";
import { useChatContextWindow } from "./hooks/useChatContextWindow";
import { useBrowserToolDetection } from "./hooks/useBrowserToolDetection";
import { useSkillRecordingWorkflow } from "./hooks/useSkillRecordingWorkflow";
import { listDockFilePathsForTree } from "./utils/dockFilePath";
import {
  shouldJumpToChromeInstall,
  WORKBENCH_BROWSER_PATH,
} from "./utils/chromeInstallGate";
import { isFileToolName } from "./constants";
import { browserApi } from "../../api/modules/browser";
import { octopThreadsApi } from "../../api/modules/octopThreads";
import type { TokenUsage } from "../../api/types";
import type { ChatAttachment } from "./hooks/useChat";
import MessageList from "./components/MessageList";
import ChatInput, { type ChatInputHandle } from "./components/ChatInput";
import WelcomeScreen from "./components/WelcomeScreen";
import AgentNotReadyScreen from "./components/AgentNotReadyScreen";
import AgentProfileDrawer from "../../components/AgentProfileDrawer";
import WorkspaceDrawer from "../Agent/Workspace/components/WorkspaceDrawer";
import { useExpertChatWelcome } from "./hooks/useExpertQuickCards";
import { useSkills } from "../Agent/Skills/useSkills";
import {
  useAgent,
  selectEnabledExperts,
  projectChatAgentOption,
} from "../../context/AgentContext";
import { useLayoutMode } from "../../context/LayoutModeContext";
import { useBrowserSessionState } from "../../hooks/useBrowserSessionState";
import { prefetchVoiceConfig } from "../../hooks/useVoiceConfig";
import { isSharedExpertViewer } from "../../utils/sharedExpert";
import ChatDockPanels from "./components/ChatDockPanels";
import { ChatFilePreviewProvider } from "./ChatFilePreviewContext";
import {
  ChatToolDockProvider,
  dockTabIdForToolCall,
} from "./ChatToolDockContext";
import ChatSidebarPanel from "./components/ChatSidebarPanel";
import ChatTitleBar from "./components/ChatTitleBar";
import ChatComposerChrome from "./components/ChatComposerChrome";
import AskQuestionCard from "./components/AskQuestionCard";
import { extractAskQuestions, isAskHitl } from "../../api/types/hitl";
import { isAgentChatReady } from "../../utils/agentError";
import { useMemoryMaintenance } from "./hooks/useMemoryMaintenance";
import MemoryMaintenanceBanner from "./components/MemoryMaintenanceBanner";
import { useHistoryMigration } from "./hooks/useHistoryMigration";
import HistoryMigrationBanner from "./components/HistoryMigrationBanner";
import { apiErrorMessage } from "../../utils/apiError";
import PwaInstallPrompt from "../../components/PwaInstallPrompt";
import { promptNeedsUserInput } from "../../utils/quickInputPrefill";
import { OPEN_NAV_RECORDS_EVENT } from "../../layouts/chatHistoryRail";
import {
  usePluginToolUis,
  setPluginUiDockHandlers,
} from "../../plugins/toolRenderers";
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
  usePluginToolUis({
    agentId: routeAgentId ?? null,
    threadId: threadId ?? null,
  });
  const isMobile = useIsMobile();
  const user = useCurrentUser();
  const { layoutMode } = useLayoutMode();
  const isMinimalLayout = layoutMode === "minimal";
  const canTerminal = userCan(user, "terminal");
  const chatHistoryRail = useChatHistoryRail();
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
    isSidebarResizing,
    sidebarElRef,
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
  const sharedExpertViewer = isSharedExpertViewer(activeAgent ?? {});
  const noAgents = !agentsLoading && agents.length === 0;

  // Sidebar only lists "enabled" experts (harness running). Stopped / failed
  // experts are hidden so the nav stays focused on agents that can actually
  // chat right now — including the focused expert the user just stopped. The
  // main panel still renders ``AgentNotReadyScreen`` on the same URL so users
  // see a clear path back to ``/experts`` to re-enable it.
  const sidebarAgents = useMemo(
    () => selectEnabledExperts(agents, resolvedAgentId, { pinActive: false }),
    [agents, resolvedAgentId],
  );

  const {
    status: memoryMaint,
    visible: memoryMaintVisible,
    blocking: memoryMaintBlocking,
  } = useMemoryMaintenance(resolvedAgentId, agentChatReady && !noAgents);
  const historyMigration = useHistoryMigration(
    resolvedAgentId,
    agentChatReady && !noAgents && !sharedExpertViewer,
  );

  useEffect(() => {
    void refreshAgents({ silent: true });
  }, [refreshAgents]);

  const { quickCards: expertQuickCards, welcomeSuffix } =
    useExpertChatWelcome(activeAgent);
  const { skills: chatSkills } = useSkills(
    agentChatReady && !agentsLoading && !sharedExpertViewer
      ? resolvedAgentId ?? null
      : null,
  );
  const [agentProfileOpen, setAgentProfileOpen] = useState(false);
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = useState(false);

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

  // Agent profile is agent-scoped — close when switching between two agents.
  const prevProfileAgentRef = useRef(resolvedAgentId);
  useEffect(() => {
    const prev = prevProfileAgentRef.current;
    prevProfileAgentRef.current = resolvedAgentId;
    if (prev == null || resolvedAgentId == null || prev === resolvedAgentId) {
      return;
    }
    setAgentProfileOpen(false);
    setWorkspaceDrawerOpen(false);
  }, [resolvedAgentId]);

  // Weak stream resume may skip intermediate tokens — hint once after rebind.
  useEffect(() => {
    return chatStore.onStreamEvent((event) => {
      if (event.kind === "streamResume") {
        const key = activeThreadId || "__empty__";
        if (event.sessionId !== key) return;
        antMessage.info(t("chat.streamResumed"));
        return;
      }
      if (event.kind !== "streamEnd") return;
      const key = activeThreadId || "__empty__";
      if (event.sessionId !== key || !resolvedAgentId || key === "__empty__") {
        return;
      }
      void fetchAndSyncSessionArtifacts(resolvedAgentId, key);
    });
  }, [activeThreadId, resolvedAgentId, t]);

  // Refresh thread artifacts after file-producing tools finish (mid-turn updates).
  useEffect(() => {
    return chatStore.onToolEvent((event) => {
      if (event.kind !== "toolDone") return;
      const key = activeThreadId || "__empty__";
      if (event.sessionId !== key || !resolvedAgentId || key === "__empty__") {
        return;
      }
      if (!isFileToolName(event.toolName)) return;
      void fetchAndSyncSessionArtifacts(resolvedAgentId, key);
    });
  }, [activeThreadId, resolvedAgentId]);

  const {
    messages,
    isStreaming,
    thinkingStartedAt,
    historyLoading,
    historyHasMore,
    historyLoadingMore,
    historyRefreshing,
    historyHydrated,
    contextUsage,
    sendMessage,
    editAndResend,
    cancelStream,
    loadHistory,
    loadMoreHistory,
    refreshHistory,
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
    dockOpen,
    dockMode,
    openTabs,
    activeTabId,
    panelSizes: dockPanelSizes,
    isResizing: dockIsResizing,
    handleResizeStart: dockHandleResizeStart,
    handleClose: handleDockClose,
    handleModeChange: handleDockModeChange,
    openFileList,
    openFileAt,
    openBrowserTab,
    toggleBrowserPanel,
    toggleTerminalPanel,
    openToolUiTab,
    focusToolUiTab,
    closeTab: closeDockTab,
    setActiveTab: setDockActiveTab,
  } = useChatDockPanel(isMobile, resolvedAgentId);

  const chromeCheckInFlightRef = useRef(false);
  const handleToggleBrowserPanel = useCallback(async () => {
    // A live session means Chrome is already running — skip the probe.
    if (browserSessionId) {
      toggleBrowserPanel();
      return;
    }
    if (chromeCheckInFlightRef.current) return;
    chromeCheckInFlightRef.current = true;
    try {
      const env = await browserApi.checkEnvStatus();
      if (shouldJumpToChromeInstall(env)) {
        showConfirmModal(
          {
            title: t("browserWorkspace.chromeMissingJumpToInstall"),
            okText: t("common.confirm"),
            cancelText: t("common.cancel"),
            onOk: () => {
              navigate(WORKBENCH_BROWSER_PATH);
            },
          },
          { isMobile },
        );
        return;
      }
    } catch {
      // Probe failed — keep the existing open-panel behavior.
    } finally {
      chromeCheckInFlightRef.current = false;
    }
    toggleBrowserPanel();
  }, [browserSessionId, isMobile, navigate, t, toggleBrowserPanel]);

  const closeToolUiPanel = useCallback(
    (callId: string) => {
      closeDockTab(dockTabIdForToolCall(callId));
    },
    [closeDockTab],
  );

  useEffect(() => {
    setPluginUiDockHandlers({
      openSidePanel: openToolUiTab,
      closeSidePanel: closeToolUiPanel,
    });
    return () => setPluginUiDockHandlers({});
  }, [openToolUiTab, closeToolUiPanel]);

  const composerSession = useMemo(
    () => sessions.find((session) => session.id === activeThreadId) ?? null,
    [sessions, activeThreadId],
  );

  const panelFilePaths = useMemo(() => {
    const fromTabs = openTabs
      .filter((tab) => tab.kind === "file")
      .map((tab) => tab.path);
    const fromThread = composerSession?.artifacts ?? [];
    return listDockFilePathsForTree(
      [...fromThread, ...fromTabs],
      resolvedAgentId,
    );
  }, [openTabs, resolvedAgentId, composerSession?.artifacts]);

  const {
    selectedModel,
    setSelectedModel,
    selectedConnectors,
    selectedSkills,
    selectedKnowledgeBaseIds,
    chatConnectors,
    chatKnowledgeBases,
    availableModels,
    activeModelRef,
    reasoningMode,
    reasoningEffort,
    handleReasoningChange,
    handleConnectorsChange,
    handleSkillsChange,
    handleKnowledgeBaseIdsChange,
  } = useChatComposerResources(
    resolvedAgentId,
    chatSkills,
    activeThreadId,
    composerSession?.modelRef,
    composerSession?.reasoningMode,
    composerSession?.reasoningEffort,
  );

  const { contextMaxTokens, contextUsedTokens } = useChatContextWindow(
    messages,
    contextUsage,
    selectedModel,
    availableModels,
    activeAgent?.default_model,
    activeModelRef,
    activeAgent,
  );

  const sessionUsage = useMemo(() => {
    const acc: TokenUsage = {};
    for (const msg of messages) {
      const u = msg.usage;
      if (!u) continue;
      if (typeof u.input_tokens === "number") {
        acc.input_tokens = (acc.input_tokens || 0) + u.input_tokens;
      }
      if (typeof u.cache_read_tokens === "number") {
        acc.cache_read_tokens =
          (acc.cache_read_tokens || 0) + u.cache_read_tokens;
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
    cacheHit: t("chatUsage.cacheHit"),
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

  // Full projection — used by surfaces that render an *existing* agent chip
  // (the preview bar above the composer and historical message chips). They
  // must still find an expert that was running when the user picked it but
  // has since been stopped, otherwise the chip silently vanishes.
  const chatAgentOptions = useMemo(
    () => agents.map(projectChatAgentOption),
    [agents],
  );
  // Subset for the chat-side *pickers* (`@` button popover, `@` mention menu).
  // Only running experts — picking a stopped one would dispatch into an
  // unloaded harness and silently fail.
  const chatAgentOptionsPickable = useMemo(
    () =>
      selectEnabledExperts(agents, null, { pinActive: false }).map(
        projectChatAgentOption,
      ),
    [agents],
  );

  const composerLookups = useMemo(
    () => ({
      skills: chatSkills,
      connectors: chatConnectors,
      knowledgeBases: chatKnowledgeBases,
      agents: chatAgentOptions,
    }),
    [chatSkills, chatConnectors, chatKnowledgeBases, chatAgentOptions],
  );

  const { handleSend } = useChatSend({
    resolvedAgentId,
    activeThreadId,
    sessions,
    messagesLength: messages.length,
    selectedModel,
    selectedConnectors,
    selectedKnowledgeBaseIds,
    selectedSkills,
    selectedTargetAgents,
    reasoningMode,
    reasoningEffort,
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
    (
      text: string,
      attachments?: ChatAttachment[],
      overrides?: ChatSendOverrides,
    ) => {
      if (interceptUserMessage(text)) {
        // The workflow intercepted the message — don't send it to the agent
        return;
      }
      handleSend(text, attachments, overrides);
    },
    [interceptUserMessage, handleSend],
  );

  const flushQueuedItem = useCallback(
    (item: QueuedChatItem, ctx: ChatQueueFlushContext): boolean => {
      if (!ctx.threadId) {
        antMessage.error(t("chat.queue.flushFailed"));
        return false;
      }
      // Bypass skill-recording intercept — queued text must not be swallowed
      // after it has already left the queue. Target the queued thread/agent so
      // background streamEnd flushes do not send into the active session.
      const ok = handleSend(item.text, item.attachments, {
        composerContext: item.composerContext,
        modelRef: item.modelRef,
        selectedModel: item.composerContext?.model ?? item.modelRef ?? null,
        selectedSkills: item.composerContext?.skills,
        selectedConnectors: item.composerContext?.connectors,
        selectedKnowledgeBaseIds: item.composerContext?.knowledgeBaseIds,
        selectedTargetAgents: item.composerContext?.targetAgents,
        threadId: ctx.threadId,
        agentId: ctx.agentId || undefined,
      });
      if (!ok) {
        antMessage.error(t("chat.queue.flushFailed"));
      }
      return ok;
    },
    [handleSend, t],
  );

  const {
    items: queuedItems,
    enqueue: enqueueQueued,
    remove: removeQueued,
    reclaim: reclaimQueued,
    clear: clearQueued,
  } = useChatMessageQueue({
    agentId: resolvedAgentId,
    threadId: activeThreadId,
    isStreaming,
    onFlush: flushQueuedItem,
  });

  const {
    handleNewChat: startNewChat,
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

  const handleNewChat = useCallback(() => {
    clearQueued();
    startNewChat();
  }, [clearQueued, startNewChat]);

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
      if (promptNeedsUserInput(text)) {
        prefillInputRef.current = trimmed;
        chatInputRef.current?.setPrefillText(trimmed);
        return;
      }
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

  const [forking, setForking] = useState(false);
  const hasPendingHitl = useMemo(
    () => messages.some((message) => message.hitlData?.status === "pending"),
    [messages],
  );
  const pendingAsk = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      const hitl = message.hitlData;
      if (
        !hitl ||
        (hitl.status ?? "pending") !== "pending" ||
        !isAskHitl(hitl.action_requests)
      ) {
        continue;
      }
      const questions = extractAskQuestions(hitl.action_requests);
      if (questions.length > 0) {
        return { id: message.id, actions: hitl.action_requests, questions };
      }
    }
    return null;
  }, [messages]);
  const forkDisabled = forking || isStreaming || hasPendingHitl;
  const forkDisabledHint =
    !forking && (isStreaming || hasPendingHitl)
      ? t("chat.forkDisabledWhileBusy")
      : undefined;
  const hasAssistantReply = useMemo(
    () =>
      messages.some(
        (message) =>
          message.role === "assistant" &&
          !message.toolData &&
          Boolean(
            (message.content && message.content.trim()) ||
              (message.attachments && message.attachments.length > 0),
          ),
      ),
    [messages],
  );
  const sessionForkDisabled = forkDisabled || !hasAssistantReply;
  const sessionForkDisabledHint = !hasAssistantReply
    ? t("chat.forkNoAssistant")
    : forkDisabledHint;

  const navigateToForkedThread = useCallback(
    async (
      agent: string,
      created: { thread_id: string; copied_messages: number },
    ) => {
      await ensureThreadInList(created.thread_id);
      navigate(`/chat/${agent}/${created.thread_id}`);
      antMessage.success(
        created.copied_messages > 0
          ? t("chat.forkSuccess")
          : t("chat.forkSuccessEmpty"),
      );
    },
    [ensureThreadInList, navigate, t],
  );

  const handleForkAssistantMessage = useCallback(
    async (messageId: string) => {
      const agent = resolvedAgentId;
      if (!agent || !activeThreadId || forkDisabled) return;
      const idx = messages.findIndex((message) => message.id === messageId);
      if (idx < 0) return;
      const assistantMsg = messages[idx];
      if (assistantMsg.role !== "assistant" || assistantMsg.toolData) return;
      const turnsFromEnd = assistantTurnsFromEnd(messages, messageId);
      if (turnsFromEnd < 1) return;
      setForking(true);
      try {
        const created = await octopThreadsApi.fork(agent, activeThreadId, {
          message_id: messageId,
          content: assistantMsg.content,
          assistant_turns_from_end: turnsFromEnd,
        });
        await navigateToForkedThread(agent, created);
      } catch (error) {
        antMessage.error(apiErrorMessage(error, t("chat.forkFailed"), t));
      } finally {
        setForking(false);
      }
    },
    [
      activeThreadId,
      forkDisabled,
      messages,
      navigateToForkedThread,
      resolvedAgentId,
      t,
    ],
  );

  const handleForkSession = useCallback(
    async (threadId: string, agentId?: string | null) => {
      const agent = agentId || resolvedAgentId;
      if (!agent || !threadId || forking) return;
      if (threadId === activeThreadId && (isStreaming || hasPendingHitl)) {
        antMessage.warning(t("chat.forkDisabledWhileBusy"));
        return;
      }
      if (threadId === activeThreadId && !hasAssistantReply) {
        antMessage.warning(t("chat.forkNoAssistant"));
        return;
      }
      setForking(true);
      try {
        const created = await octopThreadsApi.fork(agent, threadId, {
          assistant_turns_from_end: 1,
        });
        await navigateToForkedThread(agent, created);
      } catch (error) {
        antMessage.error(apiErrorMessage(error, t("chat.forkFailed"), t));
      } finally {
        setForking(false);
      }
    },
    [
      activeThreadId,
      forking,
      hasAssistantReply,
      hasPendingHitl,
      isStreaming,
      navigateToForkedThread,
      resolvedAgentId,
      t,
    ],
  );

  const hasMessages = messages.length > 0;
  // On hard refresh / deep-link into a thread, messages start empty. Showing
  // Welcome until history returns looks like a full page flash. Keep the list
  // shell while that thread is still hydrating.
  const awaitingThreadHistory = Boolean(
    activeThreadId && !hasMessages && (historyLoading || !historyHydrated),
  );
  const showWelcome = !hasMessages && !awaitingThreadHistory;
  const activeSession = useMemo(() => {
    if (!activeThreadId || showWelcome) return null;
    return (
      sessions.find((s) => s.id === activeThreadId) ?? {
        id: activeThreadId,
        name: "New Chat",
        threadId: activeThreadId,
        updatedAt: null,
        channelType: "dashboard",
        isActive: true,
        hasActivity: true,
        pinned: false,
      }
    );
  }, [activeThreadId, sessions, showWelcome]);

  const activeSessionTitle = useMemo(() => {
    if (!activeSession) return null;
    const name = activeSession.name?.trim();
    if (!name || name === "New Chat") return t("chatWelcome.newChat");
    return name;
  }, [activeSession, t]);

  const chatSidebarPanel = (
    <ChatSidebarPanel
      isMobile={isMobile}
      sidebarOpen={sidebarOpen}
      sidebarWidth={sidebarWidth}
      isSidebarResizing={isSidebarResizing}
      sidebarElRef={sidebarElRef}
      agents={sidebarAgents}
      sessions={sessions}
      activeThreadId={activeThreadId}
      resolvedAgentId={resolvedAgentId}
      sessionsHasMore={sessionsHasMore}
      sessionsLoadingMore={sessionsLoadingMore}
      onLoadMoreSessions={handleLoadMoreSessions}
      onFetchAllSessions={handleFetchAllSessions}
      onSelectSession={(sessionId, agentId) => {
        setActiveAgent(agentId);
        if (agentId && agentId !== resolvedAgentId) {
          void octopThreadsApi.rebind(agentId, sessionId).catch(() => {});
          navigate(`/chat/${agentId}/${sessionId}`);
          if (isMobile) setSidebarOpen(false);
          return;
        }
        handleSelectSession(sessionId);
      }}
      onAgentSelect={navigateToAgent}
      onDeleteSession={handleDeleteSession}
      onRenameSession={renameSession}
      onPinSession={pinSession}
      onForkSession={handleForkSession}
      forkDisabled={sessionForkDisabled}
      forkDisabledHint={sessionForkDisabledHint}
      onSidebarOpenChange={setSidebarOpen}
      onSidebarResizeStart={handleSidebarResizeStart}
      layoutRail={!isMinimalLayout}
      navEmbedded={isMinimalLayout}
    />
  );

  return (
    <ChatFilePreviewProvider openFilePreview={openFileAt}>
      <ChatToolDockProvider
        dockOpen={dockOpen}
        openTabs={openTabs}
        activeTabId={activeTabId}
        openToolUiPanel={openToolUiTab}
        closeToolUiPanel={closeToolUiPanel}
        focusToolUiPanel={focusToolUiTab}
      >
        {chatHistoryRail
          ? createPortal(chatSidebarPanel, chatHistoryRail)
          : null}
        <div
          className={`${styles.chatPage} ${
            dockIsResizing ? styles.panelResizeActive : ""
          } ${
            dockOpen && dockMode === "bottom"
              ? styles.chatPageWithBottomDock
              : ""
          }`}
        >
          {/* Main chat area */}
          <div className={styles.chatMain}>
            {/* Mobile toolbar — session list + optional title + agent profile */}
            {isMobile && (
              <div className={styles.mobileToolbar}>
                <button
                  className={styles.menuBtn}
                  onClick={() => {
                    if (isMinimalLayout) {
                      window.dispatchEvent(new Event(OPEN_NAV_RECORDS_EVENT));
                      return;
                    }
                    setSidebarOpen(!sidebarOpen);
                  }}
                  title={t("nav.chatHistory") || "会话列表"}
                >
                  <PanelLeftOpen size={18} strokeWidth={1.8} />
                </button>
                {activeSessionTitle && (
                  <div
                    className={styles.mobileTitle}
                    title={activeSessionTitle}
                  >
                    {activeSessionTitle}
                  </div>
                )}
                {resolvedAgentId && !sharedExpertViewer && (
                  <div className={styles.mobileToolbarRight}>
                    <button
                      className={styles.menuBtn}
                      onClick={() => setAgentProfileOpen(true)}
                      title={t("chat.agentProfile.open")}
                      aria-label={t("chat.agentProfile.open")}
                    >
                      <GraduationCap size={18} strokeWidth={1.8} />
                    </button>
                    <button
                      className={styles.menuBtn}
                      onClick={() => setWorkspaceDrawerOpen(true)}
                      disabled={!agentChatReady}
                      title={
                        agentChatReady
                          ? t("chat.openWorkspace", "工作区")
                          : t("workspace.requiresRunning")
                      }
                      aria-label={t("chat.openWorkspace", "工作区")}
                    >
                      <FolderOpen size={18} strokeWidth={1.8} />
                    </button>
                  </div>
                )}
              </div>
            )}

            {!isMobile && activeSession && activeSessionTitle && (
              <ChatTitleBar
                session={activeSession}
                title={activeSessionTitle}
                onRename={renameSession}
                onPin={pinSession}
                onFork={handleForkSession}
                onDelete={handleDeleteSession}
                forkDisabled={sessionForkDisabled}
                forkDisabledHint={sessionForkDisabledHint}
              />
            )}

            {memoryMaintVisible && memoryMaint && (
              <MemoryMaintenanceBanner
                status={memoryMaint}
                blocking={memoryMaintBlocking}
              />
            )}

            {historyMigration.visible && historyMigration.status && (
              <HistoryMigrationBanner
                status={historyMigration.status}
                starting={historyMigration.starting}
                startFailed={historyMigration.startFailed}
                onStart={() => void historyMigration.start()}
              />
            )}

            <div className={styles.chatContent}>
              {!agentChatReady || noAgents ? (
                <AgentNotReadyScreen
                  agent={activeAgent}
                  noAgents={noAgents}
                  loading={agentsLoading}
                />
              ) : showWelcome ? (
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
                  loading={awaitingThreadHistory}
                  historyHasMore={historyHasMore}
                  historyLoadingMore={historyLoadingMore}
                  historyRefreshing={historyRefreshing}
                  onLoadMoreHistory={loadMoreHistory}
                  onRefreshHistory={refreshHistory}
                  isStreaming={isStreaming}
                  thinkingStartedAt={thinkingStartedAt}
                  sessionKey={activeThreadId ?? undefined}
                  onCancel={cancelStream}
                  onRegenerate={handleRegenerate}
                  onEditUserMessage={handleEditUserMessage}
                  onForkAssistantMessage={handleForkAssistantMessage}
                  forkDisabled={forkDisabled}
                  forkDisabledHint={forkDisabledHint}
                  onAcpPermissionSelect={handleAcpPermissionSelect}
                  onHitlDecision={handleHitlDecision}
                  onOpenBrowser={
                    hasBrowserTool && !isMobile ? openBrowserTab : undefined
                  }
                  onEditFile={
                    !sharedExpertViewer &&
                    panelFilePaths.length > 0 &&
                    !isMobile
                      ? openFileList
                      : undefined
                  }
                />
              )}
            </div>

            {!isMobile &&
              !dockOpen &&
              !agentProfileOpen &&
              !workspaceDrawerOpen && (
                <div className={styles.chatFloatActions}>
                  {/* PWA install first when available — same column as browser / experts. */}
                  <PwaInstallPrompt appearance="chatFloat" />
                  {resolvedAgentId && !sharedExpertViewer && (
                    <>
                      <Tooltip
                        title={t("chat.agentProfile.open")}
                        mouseEnterDelay={0.35}
                        placement="left"
                      >
                        <span className={styles.chatFloatBtnWrap}>
                          <button
                            type="button"
                            className={styles.agentProfileBtn}
                            onClick={() => setAgentProfileOpen(true)}
                            aria-label={t("chat.agentProfile.open")}
                          >
                            <GraduationCap size={20} strokeWidth={2.1} />
                          </button>
                        </span>
                      </Tooltip>
                      <Tooltip
                        title={
                          agentChatReady
                            ? t("chat.openWorkspace", "工作区")
                            : t("workspace.requiresRunning")
                        }
                        mouseEnterDelay={0.35}
                        placement="left"
                      >
                        <span className={styles.chatFloatBtnWrap}>
                          <button
                            type="button"
                            className={styles.chatFloatBtn}
                            disabled={!agentChatReady}
                            onClick={() => setWorkspaceDrawerOpen(true)}
                            aria-label={t("chat.openWorkspace", "工作区")}
                          >
                            <FolderOpen size={20} strokeWidth={2.1} />
                          </button>
                        </span>
                      </Tooltip>
                    </>
                  )}
                  {!sharedExpertViewer && panelFilePaths.length > 0 && (
                    <Tooltip
                      title={t("chat.modifiedFiles", {
                        count: panelFilePaths.length,
                        defaultValue: "已修改文件（{{count}}）",
                      })}
                      mouseEnterDelay={0.35}
                      placement="left"
                    >
                      <span className={styles.chatFloatBtnWrap}>
                        <button
                          type="button"
                          className={styles.chatFloatBtn}
                          onClick={() => openFileList()}
                          aria-label={t("chat.modifiedFiles", {
                            count: panelFilePaths.length,
                            defaultValue: "已修改文件（{{count}}）",
                          })}
                        >
                          <FilePen size={20} strokeWidth={2.1} />
                        </button>
                        {panelFilePaths.length > 1 && (
                          <span className={styles.chatFloatBadge}>
                            {panelFilePaths.length > 99
                              ? "99+"
                              : panelFilePaths.length}
                          </span>
                        )}
                      </span>
                    </Tooltip>
                  )}
                  {canTerminal && (
                    <Tooltip
                      title={t("chat.openTerminal", "打开终端")}
                      mouseEnterDelay={0.35}
                      placement="left"
                    >
                      <span className={styles.chatFloatBtnWrap}>
                        <button
                          type="button"
                          className={styles.terminalFloatBtn}
                          onClick={toggleTerminalPanel}
                          aria-label={t("chat.openTerminal", "打开终端")}
                        >
                          <Terminal size={20} strokeWidth={2.1} />
                        </button>
                      </span>
                    </Tooltip>
                  )}
                  <Tooltip
                    title={
                      browserSessionId
                        ? t("browserWorkspace.browserStatusActive", {
                            owner:
                              browserControlOwner === "agent"
                                ? t("browserWorkspace.agentControl")
                                : t("browserWorkspace.userTakeover"),
                          })
                        : t("browserWorkspace.browserStatusIdle")
                    }
                    mouseEnterDelay={0.35}
                    placement="left"
                  >
                    <span className={styles.chatFloatBtnWrap}>
                      <button
                        type="button"
                        className={[
                          styles.browserStatusBtn,
                          browserSessionId ? styles.browserStatusActive : "",
                          browserSessionId &&
                          (browserSessionState === "awaiting_user_auth" ||
                            browserSessionState === "authenticating")
                            ? styles.browserStatusAuth
                            : "",
                          browserSessionId && browserControlOwner === "user"
                            ? styles.browserStatusTakeover
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        onClick={() => void handleToggleBrowserPanel()}
                        aria-label={t("chat.openBrowser")}
                      >
                        <Globe size={20} strokeWidth={2.1} />
                        {browserSessionId && (
                          <span
                            className={`${styles.browserStatusDot} ${
                              styles[`browserStatus_${browserControlOwner}`]
                            }`}
                          />
                        )}
                      </button>
                    </span>
                  </Tooltip>
                </div>
              )}

            <ChatComposerChrome sessionUsageLabel={sessionUsageLabel} />
            {pendingAsk ? (
              <div className={styles.askQuestionDock}>
                <div className={styles.askQuestionDockInner}>
                  <AskQuestionCard
                    key={pendingAsk.id}
                    questions={pendingAsk.questions}
                    status="pending"
                    onSubmit={(answer) =>
                      handleHitlDecision(
                        pendingAsk.actions.map(() => ({
                          type: "respond",
                          message: answer,
                        })),
                      )
                    }
                  />
                </div>
              </div>
            ) : null}
            <ChatInput
              ref={chatInputRef}
              onSend={wrappedHandleSend}
              onQueue={enqueueQueued}
              queuedItems={queuedItems}
              onRemoveQueued={removeQueued}
              onReclaimQueued={reclaimQueued}
              onCancel={cancelStream}
              onNewChat={handleNewChat}
              isStreaming={isStreaming}
              disabled={!agentChatReady || noAgents || memoryMaintBlocking}
              initialText={prefillInputRef.current}
              onComposerCleared={() => {
                prefillInputRef.current = "";
              }}
              availableModels={availableModels}
              selectedModel={selectedModel}
              onModelChange={setSelectedModel}
              reasoningMode={reasoningMode}
              reasoningEffort={reasoningEffort}
              onReasoningChange={handleReasoningChange}
              availableConnectors={chatConnectors}
              selectedConnectors={selectedConnectors}
              onConnectorsChange={handleConnectorsChange}
              availableKnowledgeBases={chatKnowledgeBases}
              selectedKnowledgeBaseIds={selectedKnowledgeBaseIds}
              onKnowledgeBaseIdsChange={handleKnowledgeBaseIdsChange}
              availableSkills={chatSkills}
              selectedSkills={selectedSkills}
              onSkillsChange={handleSkillsChange}
              availableAgents={chatAgentOptions}
              availableExperts={chatAgentOptionsPickable}
              selectedTargetAgents={selectedTargetAgents}
              onTargetAgentsChange={setSelectedTargetAgents}
              agentId={resolvedAgentId}
              threadId={activeThreadId}
              defaultModel={activeAgent?.default_model ?? null}
              contextUsedTokens={contextUsedTokens}
              contextMaxTokens={contextMaxTokens}
            />
          </div>

          <ChatDockPanels
            isMobile={isMobile}
            dockOpen={dockOpen}
            dockMode={dockMode}
            isResizing={dockIsResizing}
            panelSizes={dockPanelSizes}
            agentId={resolvedAgentId ?? ""}
            filePaths={sharedExpertViewer ? [] : panelFilePaths}
            openTabs={openTabs}
            activeTabId={activeTabId}
            onSelectTab={setDockActiveTab}
            onCloseTab={closeDockTab}
            onOpenFile={openFileAt}
            browserEnvironment={browserEnvironment}
            threadId={activeThreadId}
            isStreamingTurn={isStreaming}
            onModeChange={handleDockModeChange}
            onClose={handleDockClose}
            onResizeStart={dockHandleResizeStart}
          />

          {!sharedExpertViewer && (
            <>
              <AgentProfileDrawer
                open={agentProfileOpen}
                agent={activeAgent}
                isMobile={isMobile}
                onClose={() => setAgentProfileOpen(false)}
              />
              <WorkspaceDrawer
                agentId={resolvedAgentId ?? ""}
                open={workspaceDrawerOpen}
                onClose={() => setWorkspaceDrawerOpen(false)}
              />
            </>
          )}
        </div>
      </ChatToolDockProvider>
    </ChatFilePreviewProvider>
  );
}
