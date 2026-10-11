import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Send,
  Square,
  MessageSquarePlus,
  Paperclip,
  FileUp,
  FolderUp,
  Zap,
  Link2,
  Sparkles,
  Wand2,
  Mic,
  CircleDot,
  Play,
  Loader2,
  Cpu,
  Brain,
  GraduationCap,
  BookOpen,
  Bot,
  Plus,
  Check,
  ChevronLeft,
  ChevronRight,
  Route,
  Info,
  Search,
} from "lucide-react";
import { Tooltip, Popover } from "antd";
import { message } from "@/utils/antdMessage";
import type { ResolvedModel } from "../../../api/types";
import type { KnowledgeBase } from "../../../api/modules/knowledgeBases";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import type { AgentSubagentSummary } from "../../../api/modules/subagents";
import {
  modelOptionLabel,
  modelOptionValue,
} from "../../../utils/modelOptions";
import { customProviderLogo, getProviderLogo } from "../../../assets/providers";
import ContextWindowRing from "./ContextWindowRing";
import SkillPickerPopover from "./SkillPickerPopover";
import ExpertPickerPopover from "./ExpertPickerPopover";
import SubagentPickerPopover from "./SubagentPickerPopover";
import ConnectorPickerPopover from "./ConnectorPickerPopover";
import KnowledgePickerPopover from "./KnowledgePickerPopover";
import {
  ConversationModeMenu,
  conversationModeIcon,
} from "./ConversationModePicker";
import HitlPolicyPicker from "./HitlPolicyPicker";
import SlashCommandMenu from "./SlashCommandMenu";
import type { SlashMenuGroup } from "../../../utils/slashCategories";
import type { SlashMenuItem } from "../hooks/useSlashMentionInput";
import type { HitlSessionPolicy } from "../utils/hitlSessionPolicy";
import { SHORTCUT_ICON_TONE_CLASS } from "../utils/slashShortcutStyles";
import { isSttAvailable } from "../../../hooks/useVoiceInput";
import { parseSkillSlugsInText } from "../utils/skillSlash";
import { useSkillDisplayName } from "../../Agent/Skills/skillDisplayNames";
import {
  mentionedExpertIds,
  mentionedSubagentSlugs,
} from "../utils/expertMention";
import styles from "../index.module.less";

/** Picker opened from the composer plus menu. */
type CompactPickerKey =
  | "mode"
  | "model"
  | "connector"
  | "knowledge"
  | "skill"
  | "expert"
  | "subagent";

function resolveModelLogo(model: {
  provider_name: string;
  provider_kind: string;
}): string {
  const name = model.provider_name;
  const slug = name.toLowerCase().replace(/\s+/g, "-");
  return (
    getProviderLogo(name) ??
    getProviderLogo(name.toLowerCase()) ??
    getProviderLogo(slug) ??
    getProviderLogo(model.provider_kind) ??
    customProviderLogo
  );
}

// These browser APIs never change at runtime — compute once.
const _sttAvailable = isSttAvailable();
const PICKER_PANEL_TARGET_HEIGHT = 400;
const PICKER_PANEL_VIEWPORT_GUTTER = 16;

function capPickerPanelHeight(menuHeight: number): number {
  const available = window.innerHeight - PICKER_PANEL_VIEWPORT_GUTTER;
  return Math.max(menuHeight, Math.min(PICKER_PANEL_TARGET_HEIGHT, available));
}

function PlusMenuCount({
  count,
  className,
}: {
  count: number;
  className?: string;
}) {
  if (count <= 0) return null;
  return (
    <span
      className={`${styles.mobileOverflowItemCount}${
        className ? ` ${className}` : ""
      }`}
    >
      <span className={styles.mobileOverflowItemCountText}>{count}</span>
    </span>
  );
}

interface ChatInputActionsRowProps {
  isMobile: boolean;
  isStreaming: boolean;
  /** Team host room — stop control uses clearer wording. */
  isTeam?: boolean;
  disabled?: boolean;
  canSend: boolean;
  text: string;
  polishing: boolean;
  uploading: boolean;
  recording: boolean;
  transcribing: boolean;
  /** Realtime STT streams while held down, so the mic is press-and-hold. */
  voiceHoldToTalk?: boolean;
  onVoiceStart?: () => void;
  onVoiceStop?: () => void;
  browserRecording?: boolean;
  browserReplayBusy?: boolean;
  browserLastRecordingId?: string | null;
  onStartBrowserRecording?: () => void;
  onStopBrowserRecording?: () => void;
  onReplayBrowserRecording?: () => void;
  agentId?: string | null;
  threadId?: string | null;
  contextUsedTokens?: number | null;
  contextMaxTokens?: number;
  availableModels?: ResolvedModel[];
  selectedModel?: string | null;
  defaultModel?: string | null;
  onModelChange?: (model: string | null) => void;
  reasoningMode?: "auto" | "enabled" | "disabled";
  reasoningEffort?: string | null;
  onReasoningChange?: (
    mode: "auto" | "enabled" | "disabled",
    effort: string | null,
  ) => void;
  conversationMode?: "ask" | "plan" | "craft";
  onConversationModeChange?: (mode: "ask" | "plan" | "craft") => void;
  hitlPolicy?: HitlSessionPolicy;
  onHitlPolicyChange?: (policy: HitlSessionPolicy) => void;
  availableConnectors?: {
    mcp_server_name: string;
    label: string;
    kind: string;
  }[];
  selectedConnectors?: string[];
  onConnectorsChange?: (names: string[]) => void;
  availableKnowledgeBases?: KnowledgeBase[];
  selectedKnowledgeBaseIds?: string[];
  onKnowledgeBaseIdsChange?: (ids: string[]) => void;
  availableSkills?: SkillSpec[];
  onInsertSkillCommand?: (slug: string) => void;
  availableExperts?: ChatAgentOption[];
  onInsertExpertMention?: (agent: ChatAgentOption) => void;
  availableSubagents?: AgentSubagentSummary[];
  onInsertSubagentMention?: (subagent: AgentSubagentSummary) => void;
  slashPickerGroups: SlashMenuGroup<SlashMenuItem>[] | null;
  slashMenuItems: SlashMenuItem[];
  onSlashShortcutSelect: (command: string) => void;
  onFileSelect: () => void;
  onFolderSelect: () => void;
  onNewChat: () => void;
  onPolish: () => void;
  onToggleVoice: () => void;
  onCancel: () => void;
  onSubmit: () => void;
}

export default function ChatInputActionsRow({
  isMobile,
  isStreaming,
  isTeam = false,
  disabled,
  canSend,
  text,
  polishing,
  uploading,
  recording,
  transcribing,
  voiceHoldToTalk = false,
  onVoiceStart,
  onVoiceStop,
  browserRecording = false,
  browserReplayBusy = false,
  browserLastRecordingId = null,
  onStartBrowserRecording,
  onStopBrowserRecording,
  onReplayBrowserRecording,
  agentId,
  threadId,
  contextUsedTokens = null,
  contextMaxTokens = 128_000,
  availableModels,
  selectedModel,
  onModelChange,
  reasoningMode = "auto",
  reasoningEffort = null,
  onReasoningChange,
  conversationMode = "craft",
  onConversationModeChange,
  hitlPolicy,
  onHitlPolicyChange,
  availableConnectors,
  selectedConnectors = [],
  onConnectorsChange,
  availableKnowledgeBases,
  selectedKnowledgeBaseIds = [],
  onKnowledgeBaseIdsChange,
  availableSkills,
  onInsertSkillCommand,
  availableExperts,
  onInsertExpertMention,
  availableSubagents,
  onInsertSubagentMention,
  slashPickerGroups,
  slashMenuItems,
  onSlashShortcutSelect,
  onFileSelect,
  onFolderSelect,
  onNewChat,
  onPolish,
  onToggleVoice,
  onCancel,
  onSubmit,
}: ChatInputActionsRowProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remoteManaged = Boolean(agentId?.startsWith("bridge:"));
  const skillDisplayName = useSkillDisplayName();
  const actionsRowRef = useRef<HTMLDivElement | null>(null);
  const voiceHeldRef = useRef(false);
  const [plusMenuEl, setPlusMenuEl] = useState<HTMLDivElement | null>(null);
  const [plusPanelEl, setPlusPanelEl] = useState<HTMLDivElement | null>(null);
  const [plusPanelMaxHeight, setPlusPanelMaxHeight] = useState<number | null>(
    null,
  );
  const [plusPanelAlignBottom, setPlusPanelAlignBottom] = useState(false);
  const [modelQuery, setModelQuery] = useState("");
  const [isCompact, setIsCompact] = useState(false);
  const [shortcutOpen, setShortcutOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [reasoningModelRef, setReasoningModelRef] = useState<string | null>(
    null,
  );

  // Press-and-hold dictation: start on pointerdown, finish on release or when
  // the pointer slides off the button (also covers touch cancel).
  const handleVoicePressStart = () => {
    if (voiceHeldRef.current) return;
    voiceHeldRef.current = true;
    onVoiceStart?.();
  };

  const handleVoicePressEnd = () => {
    if (!voiceHeldRef.current) return;
    voiceHeldRef.current = false;
    onVoiceStop?.();
  };
  /** Plus-button menu (model / skills / …). */
  const [overflowPopoverOpen, setOverflowPopoverOpen] = useState(false);
  /** Picker panel opened from a plus-menu item. */
  const [compactPicker, setCompactPicker] = useState<CompactPickerKey | null>(
    null,
  );

  const useCompactControls = isMobile || isCompact;

  useLayoutEffect(() => {
    if (!plusMenuEl || isMobile) {
      setPlusPanelMaxHeight(null);
      setPlusPanelAlignBottom(false);
      return;
    }
    const sync = () => {
      const menuH = Math.round(plusMenuEl.getBoundingClientRect().height);
      if (menuH > 0) {
        const capped = capPickerPanelHeight(menuH);
        setPlusPanelMaxHeight((prev) => (prev === capped ? prev : capped));
      }
      if (!plusPanelEl) {
        setPlusPanelAlignBottom(false);
        return;
      }
      const panelH = plusPanelEl.getBoundingClientRect().height;
      if (menuH > 0 && panelH > 0) {
        setPlusPanelAlignBottom(panelH > menuH);
      }
    };
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(plusMenuEl);
    if (plusPanelEl) observer.observe(plusPanelEl);
    window.addEventListener("resize", sync);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", sync);
    };
  }, [plusMenuEl, plusPanelEl, isMobile]);

  useEffect(() => {
    if (isMobile) {
      setIsCompact(false);
      return;
    }
    const row = actionsRowRef.current;
    if (!row) return;
    const update = (width: number) => setIsCompact(width <= 560);
    update(row.getBoundingClientRect().width);
    const observer = new ResizeObserver(([entry]) => {
      if (entry) update(entry.contentRect.width);
    });
    observer.observe(row);
    return () => observer.disconnect();
  }, [isMobile]);

  const showModelPicker = Boolean(
    availableModels && availableModels.length > 0 && onModelChange,
  );
  const allowWriteTools = conversationMode === "craft";
  const showConnectorPicker = Boolean(
    allowWriteTools && availableConnectors && onConnectorsChange,
  );
  const showKnowledgePicker = Boolean(
    availableKnowledgeBases && onKnowledgeBaseIdsChange,
  );
  const showSkillPicker = Boolean(
    allowWriteTools && availableSkills && onInsertSkillCommand,
  );
  const showExpertPicker = Boolean(
    allowWriteTools &&
      availableExperts &&
      onInsertExpertMention &&
      availableExperts.length > 0,
  );
  const showSubagentPicker = Boolean(
    allowWriteTools &&
      availableSubagents &&
      onInsertSubagentMention &&
      availableSubagents.length > 0,
  );
  const mentionedExperts = mentionedExpertIds(text, availableExperts ?? []);
  const mentionedSubagents = mentionedSubagentSlugs(
    text,
    availableSubagents ?? [],
  );
  const skillTokenRefs = useMemo(
    () =>
      (availableSkills ?? []).map((skill) => ({
        slug: skill.slug,
        label: skillDisplayName(skill),
        emoji: skill.emoji,
      })),
    [availableSkills, skillDisplayName],
  );
  const activeSkillSlugs = parseSkillSlugsInText(text, skillTokenRefs);
  const showModePicker = Boolean(onConversationModeChange);
  const showOverflowMenu =
    showModePicker ||
    showModelPicker ||
    showConnectorPicker ||
    showKnowledgePicker ||
    showSkillPicker ||
    showExpertPicker ||
    showSubagentPicker;

  const overflowBadgeCount =
    selectedConnectors.length +
    selectedKnowledgeBaseIds.length +
    activeSkillSlugs.length +
    mentionedExperts.length +
    mentionedSubagents.length;

  const closeCompactPicker = () => {
    setCompactPicker(null);
    setReasoningModelRef(null);
    setModelQuery("");
  };

  const closePlusMenu = () => {
    setOverflowPopoverOpen(false);
    closeCompactPicker();
  };

  const openCompactPicker = (key: CompactPickerKey) => {
    setReasoningModelRef(null);
    if (key !== "model") setModelQuery("");
    setCompactPicker((prev) => (prev === key ? null : key));
  };

  const handleExpertSelect = (agent: ChatAgentOption) => {
    onInsertExpertMention?.(agent);
    closePlusMenu();
  };

  const handleSubagentSelect = (subagent: AgentSubagentSummary) => {
    onInsertSubagentMention?.(subagent);
    closePlusMenu();
  };

  const compactPickerTitle: Record<CompactPickerKey, string> = {
    mode: t("chat.conversationMode.picker"),
    model: t("chat.selectModel", "Model"),
    connector: t("connectors.chatPicker"),
    knowledge: t("chat.knowledgePicker"),
    skill: t("chat.skillPicker"),
    expert: t("chat.expertPicker"),
    subagent: t("chat.subagentPicker"),
  };

  const reasoningModel = availableModels?.find(
    (model) => modelOptionValue(model) === reasoningModelRef,
  );
  const reasoningModelCapability = reasoningModel?.reasoning_config;

  const reasoningModeLabel = (mode: "auto" | "enabled" | "disabled") =>
    mode === "auto"
      ? t("chat.reasoningAuto", "自动")
      : mode === "enabled"
      ? t("chat.reasoningEnabled", "开启")
      : t("chat.reasoningDisabled", "关闭");

  const selectedModelTriggerLabel = selectedModel
    ? modelOptionLabel(
        availableModels?.find((m) => modelOptionValue(m) === selectedModel) ?? {
          provider_name: selectedModel.split("/")[0] || "",
          model: selectedModel.split("/").slice(1).join("/") || selectedModel,
        },
      )
    : t("chat.modelAuto", "Auto");

  const modelQueryNormalized = modelQuery.trim().toLowerCase();
  const filteredModels = (availableModels ?? []).filter((model) => {
    if (!modelQueryNormalized) return true;
    return (
      modelOptionLabel(model).toLowerCase().includes(modelQueryNormalized) ||
      model.model.toLowerCase().includes(modelQueryNormalized) ||
      model.provider_name.toLowerCase().includes(modelQueryNormalized)
    );
  });
  const autoLabel = t("chat.modelAuto", "Auto");
  const autoHint = t("chat.modelAutoHint", "Use agent default");
  const showAutoModel = !modelQueryNormalized
    ? true
    : autoLabel.toLowerCase().includes(modelQueryNormalized) ||
      autoHint.toLowerCase().includes(modelQueryNormalized);

  const reasoningSummary = (model: ResolvedModel, active: boolean) => {
    const capability = model.reasoning_config;
    if (!capability) return null;
    if (capability.adapter === "status_only") {
      return t("chat.reasoningAlways", "始终推理");
    }
    if (active) {
      return reasoningEffort || reasoningModeLabel(reasoningMode);
    }
    return (
      capability.default_effort ||
      reasoningModeLabel(capability.default_mode || "auto")
    );
  };

  const openModelReasoning = (modelRef: string) => {
    if (selectedModel !== modelRef) onModelChange?.(modelRef);
    setReasoningModelRef(modelRef);
  };

  const reasoningMenu = reasoningModelCapability ? (
    <div className={styles.reasoningMenuPanel}>
      <div className={styles.reasoningMenuHeader}>
        <button
          type="button"
          className={styles.reasoningMenuBack}
          onClick={() => setReasoningModelRef(null)}
          aria-label={t("common.back", "返回")}
        >
          <ChevronLeft size={16} />
        </button>
        <span>{reasoningModel ? modelOptionLabel(reasoningModel) : ""}</span>
      </div>
      {reasoningModelCapability.adapter === "status_only" ? (
        <div className={styles.reasoningStatusRow}>
          <Brain size={16} />
          <span>{t("chat.reasoningAlways", "始终推理")}</span>
          <Check size={16} />
        </div>
      ) : (
        <>
          <div className={styles.reasoningMenuSectionLabel}>
            {t("chat.reasoningMode", "思考模式")}
          </div>
          {(reasoningModelCapability.toggle
            ? (["auto", "enabled", "disabled"] as const)
            : (["auto", "enabled"] as const)
          ).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`${styles.reasoningMenuChoice} ${
                reasoningMode === mode ? styles.reasoningMenuChoiceActive : ""
              }`}
              onClick={() => onReasoningChange?.(mode, reasoningEffort)}
            >
              <span>{reasoningModeLabel(mode)}</span>
              {reasoningMode === mode && <Check size={16} />}
            </button>
          ))}
          {reasoningModelCapability.efforts.length > 0 && (
            <>
              <div className={styles.reasoningMenuDivider} />
              <div className={styles.reasoningMenuSectionLabel}>
                {t("chat.reasoningEffort", "思考强度")}
              </div>
              {reasoningModelCapability.efforts.map((effort) => (
                <button
                  key={effort}
                  type="button"
                  className={`${styles.reasoningMenuChoice} ${
                    reasoningEffort === effort
                      ? styles.reasoningMenuChoiceActive
                      : ""
                  }`}
                  onClick={() =>
                    onReasoningChange?.(
                      reasoningMode === "disabled" ? "enabled" : reasoningMode,
                      effort,
                    )
                  }
                >
                  <span>{effort}</span>
                  {reasoningEffort === effort && <Check size={16} />}
                </button>
              ))}
            </>
          )}
        </>
      )}
    </div>
  ) : null;

  const modelMenu = (
    <div className={styles.modelPickerPanel}>
      {!reasoningMenu && (
        <div className={styles.modelMenuColumn}>
          <div className={styles.skillPickerSearch}>
            <input
              type="search"
              className={styles.skillPickerSearchInput}
              placeholder={t("chat.modelPickerSearch", "Search models")}
              value={modelQuery}
              onChange={(event) => setModelQuery(event.target.value)}
            />
            <Search
              size={15}
              className={styles.skillPickerSearchIcon}
              aria-hidden
            />
          </div>
          <div className={styles.modelMenu}>
            {showAutoModel ? (
              <button
                type="button"
                className={`${styles.modelMenuItem} ${
                  !selectedModel ? styles.modelMenuItemActive : ""
                }`}
                onClick={() => {
                  onModelChange?.(null);
                  closePlusMenu();
                }}
              >
                <span className={styles.modelMenuTitle}>
                  <Route size={16} aria-hidden />
                  <span className={styles.modelMenuLabel}>{autoLabel}</span>
                </span>
                <span className={styles.modelMenuHint}>{autoHint}</span>
              </button>
            ) : null}
            {filteredModels.map((model) => {
              const value = modelOptionValue(model);
              const active = selectedModel === value;
              const capability = model.reasoning_config;
              const summary = reasoningSummary(model, active);
              return (
                <div
                  key={value}
                  className={`${styles.modelMenuRow} ${
                    active ? styles.modelMenuItemActive : ""
                  }`}
                >
                  <button
                    type="button"
                    className={styles.modelMenuSelect}
                    onClick={() => {
                      onModelChange?.(active ? null : value);
                      closePlusMenu();
                    }}
                  >
                    <img
                      src={resolveModelLogo(model)}
                      alt=""
                      className={styles.modelMenuIcon}
                    />
                    <span className={styles.modelMenuLabel}>
                      {modelOptionLabel(model)}
                    </span>
                  </button>
                  {capability && onReasoningChange && (
                    <button
                      type="button"
                      className={styles.modelMenuReasoning}
                      onClick={() => openModelReasoning(value)}
                      aria-label={`${modelOptionLabel(model)} ${t(
                        "chat.reasoningMode",
                        "思考模式",
                      )}`}
                    >
                      <Brain size={14} />
                      {summary && <span>{summary}</span>}
                      {capability.adapter !== "status_only" && (
                        <ChevronRight size={15} />
                      )}
                    </button>
                  )}
                </div>
              );
            })}
            {!showAutoModel && filteredModels.length === 0 ? (
              <div className={styles.skillPickerEmpty}>
                {t("chat.modelPickerEmpty", "No matching models")}
              </div>
            ) : null}
          </div>
          <div className={styles.modelMenuDivider} />
          <button
            type="button"
            className={`${styles.modelMenuFooter} ${
              remoteManaged ? styles.modelMenuFooterMuted : ""
            }`}
            onClick={() => {
              if (remoteManaged) {
                message.info(t("chat.remoteExpert.manageToast"));
                return;
              }
              closePlusMenu();
              navigate("/admin/models");
            }}
          >
            {remoteManaged ? (
              <Info size={15} aria-hidden />
            ) : (
              <Cpu size={15} aria-hidden />
            )}
            <span>
              {remoteManaged
                ? t("chat.remoteExpert.manageOnPeer")
                : t("chat.modelPickerManage")}
            </span>
          </button>
        </div>
      )}
      {reasoningMenu}
    </div>
  );

  const shortcutMenu = (
    <div className={styles.shortcutPickerPanel}>
      <div className={styles.skillPickerList}>
        <SlashCommandMenu
          groups={slashPickerGroups}
          flatItems={slashMenuItems}
          activeIndex={-1}
          disabled={isStreaming || disabled}
          variant="popover"
          itemsGridClassName={styles.slashMenuGrid}
          itemClassName={styles.slashPickerItem}
          activeClassName=""
          categoryClassName={styles.slashMenuCategory}
          labelClassName={styles.skillPickerText}
          nameClassName={styles.skillPickerName}
          cmdClassName={styles.skillPickerDesc}
          iconWrapClassName={(tone) =>
            `${styles.shortcutPickerIcon} ${
              SHORTCUT_ICON_TONE_CLASS[tone] ?? styles.shortcutPickerIconBlue
            }`
          }
          onSelect={(command) => {
            setShortcutOpen(false);
            onSlashShortcutSelect(command);
          }}
          onHover={() => undefined}
        />
      </div>
    </div>
  );

  const ModeIcon = conversationModeIcon(conversationMode);

  const renderPlusMenu = () => (
    <div className={styles.mobileOverflowMenu}>
      {showModePicker && (
        <button
          type="button"
          className={`${styles.mobileOverflowItem} ${
            compactPicker === "mode" ? styles.mobileOverflowItemActive : ""
          }`}
          onClick={() => openCompactPicker("mode")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <ModeIcon size={16} />
            <span>{t("chat.conversationMode.picker")}</span>
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            <span className={styles.mobileOverflowItemMetaLabel}>
              {t(`chat.conversationMode.${conversationMode}`)}
            </span>
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showModelPicker && (
        <button
          type="button"
          className={`${styles.mobileOverflowItem} ${
            compactPicker === "model" ? styles.mobileOverflowItemActive : ""
          }`}
          onClick={() => openCompactPicker("model")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <Cpu size={16} />
            <span>{t("chat.selectModel", "Model")}</span>
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            <span className={styles.mobileOverflowItemMetaLabel}>
              {selectedModelTriggerLabel}
            </span>
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showConnectorPicker && (
        <button
          type="button"
          className={`${styles.mobileOverflowItem} ${
            compactPicker === "connector" ? styles.mobileOverflowItemActive : ""
          }`}
          onClick={() => openCompactPicker("connector")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <Link2 size={16} />
            <span>{t("connectors.chatPicker")}</span>
            <PlusMenuCount count={selectedConnectors.length} />
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showKnowledgePicker && (
        <button
          type="button"
          className={`${styles.mobileOverflowItem} ${
            compactPicker === "knowledge" ? styles.mobileOverflowItemActive : ""
          }`}
          onClick={() => openCompactPicker("knowledge")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <BookOpen size={16} />
            <span>{t("chat.knowledgePicker")}</span>
            <PlusMenuCount count={selectedKnowledgeBaseIds.length} />
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showSkillPicker && (
        <button
          type="button"
          className={`${styles.mobileOverflowItem} ${
            compactPicker === "skill" ? styles.mobileOverflowItemActive : ""
          }`}
          onClick={() => openCompactPicker("skill")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <Sparkles size={16} />
            <span>{t("chat.skillPicker")}</span>
            <PlusMenuCount count={activeSkillSlugs.length} />
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showExpertPicker && (
        <button
          type="button"
          className={`${styles.mobileOverflowItem} ${
            compactPicker === "expert" ? styles.mobileOverflowItemActive : ""
          }`}
          onClick={() => openCompactPicker("expert")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <GraduationCap size={16} />
            <span>{t("chat.expertPicker")}</span>
            <PlusMenuCount
              count={mentionedExperts.length}
              className={styles.mobileOverflowItemCountExpert}
            />
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showSubagentPicker && (
        <button
          type="button"
          className={`${styles.mobileOverflowItem} ${
            compactPicker === "subagent" ? styles.mobileOverflowItemActive : ""
          }`}
          onClick={() => openCompactPicker("subagent")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <Bot size={16} />
            <span>{t("chat.subagentPicker")}</span>
            <PlusMenuCount
              count={mentionedSubagents.length}
              className={styles.mobileOverflowItemCountSubagent}
            />
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            <ChevronRight size={16} />
          </span>
        </button>
      )}
    </div>
  );

  const renderCompactPickerContent = () => {
    switch (compactPicker) {
      case "mode":
        return (
          <ConversationModeMenu
            conversationMode={conversationMode}
            onChange={(mode) => {
              onConversationModeChange?.(mode);
              closePlusMenu();
            }}
          />
        );
      case "model":
        return modelMenu;
      case "connector":
        return (
          <ConnectorPickerPopover
            connectors={availableConnectors ?? []}
            selectedConnectors={selectedConnectors}
            onConnectorsChange={onConnectorsChange!}
            onNavigateAway={closePlusMenu}
          />
        );
      case "knowledge":
        return (
          <KnowledgePickerPopover
            knowledgeBases={availableKnowledgeBases ?? []}
            selectedKnowledgeBaseIds={selectedKnowledgeBaseIds}
            onKnowledgeBaseIdsChange={onKnowledgeBaseIdsChange!}
            onNavigateAway={closePlusMenu}
            remoteManaged={remoteManaged}
          />
        );
      case "skill":
        return (
          <SkillPickerPopover
            skills={availableSkills ?? []}
            activeSlugs={activeSkillSlugs}
            onSelectSkill={(slug) => {
              onInsertSkillCommand?.(slug);
              closePlusMenu();
            }}
            onNavigateAway={closePlusMenu}
            remoteManaged={remoteManaged}
          />
        );
      case "expert":
        return (
          <ExpertPickerPopover
            agents={availableExperts ?? []}
            selectedAgentIds={mentionedExperts}
            onSelect={handleExpertSelect}
            onNavigateAway={closePlusMenu}
            remoteManaged={remoteManaged}
          />
        );
      case "subagent":
        return (
          <SubagentPickerPopover
            subagents={availableSubagents ?? []}
            selectedSlugs={mentionedSubagents}
            onSelect={handleSubagentSelect}
            onNavigateAway={closePlusMenu}
            remoteManaged={remoteManaged}
          />
        );
      default:
        return null;
    }
  };

  const renderSecondaryActions = () => {
    const plusButton = (
      <button
        className={`${styles.secondaryBtn} ${
          overflowBadgeCount > 0 ? styles.secondaryBtnActive : ""
        }`}
        type="button"
        aria-label={t("chat.composerMore", "更多工具")}
        data-testid="composer-plus"
      >
        <Plus size={16} />
        {overflowBadgeCount > 0 && (
          <span className={styles.toolbarBadge}>{overflowBadgeCount}</span>
        )}
      </button>
    );

    return (
      <>
        {showOverflowMenu && (
          <Popover
            trigger="click"
            placement="topLeft"
            arrow={false}
            open={overflowPopoverOpen}
            overlayClassName={styles.plusMenuPopover}
            content={
              <div className={styles.plusFlyout}>
                {!isMobile || !compactPicker ? (
                  <div ref={setPlusMenuEl} className={styles.plusFlyoutMenu}>
                    {renderPlusMenu()}
                  </div>
                ) : null}
                {compactPicker ? (
                  <div
                    ref={isMobile ? undefined : setPlusPanelEl}
                    className={
                      isMobile
                        ? styles.plusFlyoutPanelInPlace
                        : `${styles.plusFlyoutPanel}${
                            plusPanelAlignBottom
                              ? ` ${styles.plusFlyoutPanelAlignBottom}`
                              : ""
                          }`
                    }
                    style={
                      !isMobile && plusPanelMaxHeight
                        ? { maxHeight: plusPanelMaxHeight }
                        : undefined
                    }
                    data-testid="composer-plus-panel"
                    data-align={plusPanelAlignBottom ? "bottom" : "top"}
                  >
                    {isMobile ? (
                      <button
                        type="button"
                        className={styles.compactPickerBack}
                        onClick={closeCompactPicker}
                      >
                        <ChevronLeft size={16} />
                        <span>{compactPickerTitle[compactPicker]}</span>
                      </button>
                    ) : null}
                    <div className={styles.plusFlyoutPanelBody}>
                      {renderCompactPickerContent()}
                    </div>
                  </div>
                ) : null}
              </div>
            }
            onOpenChange={(open) => {
              setOverflowPopoverOpen(open);
              if (!open) closeCompactPicker();
            }}
          >
            <Tooltip
              title={t("chat.composerMore", "更多工具")}
              mouseEnterDelay={0.4}
            >
              {plusButton}
            </Tooltip>
          </Popover>
        )}
        {onHitlPolicyChange && (
          <HitlPolicyPicker
            policy={hitlPolicy ?? { mode: "ask" }}
            onChange={onHitlPolicyChange}
          />
        )}
        <Popover
          trigger="click"
          placement="topLeft"
          open={shortcutOpen}
          onOpenChange={setShortcutOpen}
          overlayClassName={styles.skillPickerPopover}
          content={shortcutMenu}
        >
          <Tooltip
            title={t("shortcut.title", "快捷指令")}
            mouseEnterDelay={0.4}
          >
            <button
              className={styles.secondaryBtn}
              type="button"
              aria-label={t("shortcut.title", "快捷指令")}
            >
              <Zap size={16} />
            </button>
          </Tooltip>
        </Popover>
        <Popover
          trigger="click"
          placement="topLeft"
          open={uploadOpen}
          onOpenChange={setUploadOpen}
          overlayClassName={styles.skillPickerPopover}
          content={
            <div className={styles.mobileOverflowMenu} role="menu">
              <button
                type="button"
                role="menuitem"
                className={styles.mobileOverflowItem}
                onClick={() => {
                  setUploadOpen(false);
                  onFileSelect();
                }}
              >
                <span className={styles.mobileOverflowItemMain}>
                  <FileUp size={16} />
                  <span>{t("upload.files", "Files")}</span>
                </span>
              </button>
              <button
                type="button"
                role="menuitem"
                className={styles.mobileOverflowItem}
                onClick={() => {
                  setUploadOpen(false);
                  onFolderSelect();
                }}
              >
                <span className={styles.mobileOverflowItemMain}>
                  <FolderUp size={16} />
                  <span>{t("upload.folder", "Folder")}</span>
                </span>
              </button>
            </div>
          }
        >
          <Tooltip title={t("upload.tooltip", "Upload")} mouseEnterDelay={0.4}>
            <button
              className={styles.secondaryBtn}
              type="button"
              disabled={uploading}
              aria-label={t("upload.tooltip", "Upload")}
              aria-haspopup="menu"
            >
              <Paperclip size={16} />
            </button>
          </Tooltip>
        </Popover>
      </>
    );
  };

  return (
    <div
      ref={actionsRowRef}
      className={`${styles.actionsRow}${
        isMobile ? ` ${styles.actionsRowCompact}` : ""
      }`}
    >
      <div className={styles.secondaryActions}>{renderSecondaryActions()}</div>
      {conversationMode !== "craft" ? (
        <p className={styles.modeHint} data-testid="conversation-mode-hint">
          <ModeIcon size={14} aria-hidden />
          <span>{t(`chat.conversationMode.${conversationMode}Reminder`)}</span>
        </p>
      ) : null}
      <div className={styles.inputActions}>
        <ContextWindowRing
          usedTokens={contextUsedTokens}
          usageEstimated={contextUsedTokens == null}
          maxTokens={contextMaxTokens}
          agentId={agentId}
          threadId={threadId}
          selectedConnectors={selectedConnectors}
          isMobile={isMobile}
        />
        {/* Desktop: dedicated newChatBtn; mobile: replace polish with new-chat */}
        {useCompactControls ? (
          <Tooltip title={t("chatWelcome.newChat")} mouseEnterDelay={0.4}>
            <button
              className={styles.newChatBtn}
              onClick={onNewChat}
              type="button"
            >
              <MessageSquarePlus size={16} strokeWidth={1.75} />
            </button>
          </Tooltip>
        ) : (
          <>
            <Tooltip title={t("chatWelcome.newChat")} mouseEnterDelay={0.4}>
              <button
                className={styles.newChatBtn}
                onClick={onNewChat}
                type="button"
              >
                <MessageSquarePlus size={16} strokeWidth={1.75} />
              </button>
            </Tooltip>
            <Tooltip title={t("chat.polish.tooltip")} mouseEnterDelay={0.4}>
              <button
                className={styles.secondaryBtn}
                onClick={onPolish}
                type="button"
                disabled={
                  !text.trim() ||
                  polishing ||
                  isStreaming ||
                  disabled ||
                  !agentId
                }
              >
                <Wand2
                  size={16}
                  className={polishing ? styles.spinIcon : undefined}
                />
              </button>
            </Tooltip>
          </>
        )}
        <Tooltip
          title={
            !_sttAvailable
              ? t("voice.sttNotAvailable", "此设备不支持语音输入（需要 HTTPS）")
              : voiceHoldToTalk
              ? recording
                ? t("voice.releaseToStop", "松开结束")
                : t("voice.holdToTalk", "按住说话")
              : recording
              ? t("voice.stopRecording", "停止录音")
              : transcribing
              ? t("voice.transcribing", "识别中…")
              : t("voice.startRecording", "语音输入")
          }
          mouseEnterDelay={0.4}
        >
          <button
            className={`${styles.secondaryBtn} ${
              recording || transcribing ? styles.secondaryBtnActive : ""
            }`}
            type="button"
            // Dictation only fills the composer, so it stays available while a
            // reply is still streaming.
            disabled={disabled || transcribing || !_sttAvailable}
            onClick={voiceHoldToTalk ? undefined : onToggleVoice}
            onPointerDown={
              voiceHoldToTalk
                ? (event) => {
                    event.preventDefault();
                    handleVoicePressStart();
                  }
                : undefined
            }
            onPointerUp={voiceHoldToTalk ? handleVoicePressEnd : undefined}
            onPointerLeave={voiceHoldToTalk ? handleVoicePressEnd : undefined}
            onPointerCancel={voiceHoldToTalk ? handleVoicePressEnd : undefined}
            onContextMenu={
              voiceHoldToTalk ? (event) => event.preventDefault() : undefined
            }
            style={
              voiceHoldToTalk
                ? { touchAction: "none", userSelect: "none" }
                : undefined
            }
          >
            <Mic size={16} />
          </button>
        </Tooltip>
        {(onStartBrowserRecording || onStopBrowserRecording) && (
          <Tooltip
            title={
              browserRecording
                ? t("browser.recordReplay.stop", "停止浏览器录制")
                : t("browser.recordReplay.start", "开始浏览器录制")
            }
            mouseEnterDelay={0.4}
          >
            <button
              className={`${styles.secondaryBtn} ${
                browserRecording ? styles.secondaryBtnRecording : ""
              }`}
              type="button"
              disabled={disabled || browserReplayBusy}
              onClick={
                browserRecording
                  ? onStopBrowserRecording
                  : onStartBrowserRecording
              }
            >
              {browserRecording ? (
                <Square size={15} />
              ) : (
                <CircleDot size={16} />
              )}
            </button>
          </Tooltip>
        )}
        {onReplayBrowserRecording && (
          <Tooltip
            title={
              browserLastRecordingId
                ? t("browser.recordReplay.replay", "回放最近一次浏览器录制")
                : t(
                    "browser.recordReplay.noRecording",
                    "请先完成一次浏览器录制",
                  )
            }
            mouseEnterDelay={0.4}
          >
            <button
              className={`${styles.secondaryBtn} ${
                browserReplayBusy ? styles.secondaryBtnActive : ""
              }`}
              type="button"
              disabled={
                disabled ||
                browserRecording ||
                browserReplayBusy ||
                !browserLastRecordingId
              }
              onClick={onReplayBrowserRecording}
            >
              {browserReplayBusy ? (
                <Loader2 size={16} className={styles.spinIcon} />
              ) : (
                <Play size={16} />
              )}
            </button>
          </Tooltip>
        )}
        {isStreaming ? (
          canSend ? (
            <Tooltip title={t("chat.queue.action")} mouseEnterDelay={0.4}>
              <button
                className={styles.sendBtn}
                onClick={onSubmit}
                title={t("chat.queue.action")}
                type="button"
                aria-label={t("chat.queue.action")}
              >
                <Send size={18} />
              </button>
            </Tooltip>
          ) : (
            <Tooltip
              title={
                isTeam
                  ? t("chat.stopTeamHint", {
                      defaultValue:
                        "停止本轮生成；已开始的成员回复可能仍会继续推送",
                    })
                  : t("chat.stop", "Stop")
              }
              mouseEnterDelay={0.4}
            >
              <button
                className={`${styles.sendBtn} ${styles.cancelBtn}`}
                onClick={onCancel}
                title={
                  isTeam
                    ? t("chat.stopTeamHint", {
                        defaultValue:
                          "停止本轮生成；已开始的成员回复可能仍会继续推送",
                      })
                    : t("chat.stop", "Stop")
                }
                type="button"
                aria-label={t("chat.stop", "Stop")}
              >
                <Square size={18} />
              </button>
            </Tooltip>
          )
        ) : (
          <button
            className={styles.sendBtn}
            onClick={onSubmit}
            disabled={!canSend}
            title={t("chat.send", "Send")}
            type="button"
          >
            <Send size={18} />
          </button>
        )}
      </div>
    </div>
  );
}
