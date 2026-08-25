import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Send,
  Square,
  MessageSquarePlus,
  Paperclip,
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
  MoreHorizontal,
  Check,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Tooltip, Popover, Drawer } from "antd";
import type { ResolvedModel } from "../../../api/types";
import type { KnowledgeBase } from "../../../api/modules/knowledgeBases";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import {
  modelOptionLabel,
  modelOptionValue,
  modelShortLabel,
} from "../../../utils/modelOptions";
import ContextWindowRing from "./ContextWindowRing";
import SkillPickerPopover from "./SkillPickerPopover";
import ExpertPickerPopover from "./ExpertPickerPopover";
import ConnectorPickerPopover from "./ConnectorPickerPopover";
import KnowledgePickerPopover from "./KnowledgePickerPopover";
import SlashCommandMenu from "./SlashCommandMenu";
import type { SlashMenuGroup } from "../../../utils/slashCategories";
import type { SlashMenuItem } from "../hooks/useSlashMentionInput";
import { SHORTCUT_ICON_TONE_CLASS } from "../utils/slashShortcutStyles";
import { isSttAvailable } from "../../../hooks/useVoiceInput";
import { resolveTurnModelOverride } from "../utils/chatMessages";
import styles from "../index.module.less";

/** Shared by mobile drawers and narrow-desktop popovers. */
type CompactPickerKey =
  | "model"
  | "connector"
  | "knowledge"
  | "skill"
  | "expert"
  | "shortcut";

// These browser APIs never change at runtime — compute once.
const _sttAvailable = isSttAvailable();

interface ChatInputActionsRowProps {
  isMobile: boolean;
  isStreaming: boolean;
  disabled?: boolean;
  canSend: boolean;
  text: string;
  polishing: boolean;
  uploading: boolean;
  recording: boolean;
  transcribing: boolean;
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
  selectedSkills?: string[];
  onSkillsChange?: (names: string[]) => void;
  availableExperts?: ChatAgentOption[];
  selectedTargetAgents?: string[];
  onTargetAgentsChange?: (ids: string[]) => void;
  slashPickerGroups: SlashMenuGroup<SlashMenuItem>[] | null;
  slashMenuItems: SlashMenuItem[];
  onSlashShortcutSelect: (command: string) => void;
  onFileSelect: () => void;
  onNewChat: () => void;
  onPolish: () => void;
  onToggleVoice: () => void;
  onCancel: () => void;
  onSubmit: () => void;
}

export default function ChatInputActionsRow({
  isMobile,
  isStreaming,
  disabled,
  canSend,
  text,
  polishing,
  uploading,
  recording,
  transcribing,
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
  defaultModel,
  onModelChange,
  reasoningMode = "auto",
  reasoningEffort = null,
  onReasoningChange,
  availableConnectors,
  selectedConnectors = [],
  onConnectorsChange,
  availableKnowledgeBases,
  selectedKnowledgeBaseIds = [],
  onKnowledgeBaseIdsChange,
  availableSkills,
  selectedSkills = [],
  onSkillsChange,
  availableExperts,
  selectedTargetAgents = [],
  onTargetAgentsChange,
  slashPickerGroups,
  slashMenuItems,
  onSlashShortcutSelect,
  onFileSelect,
  onNewChat,
  onPolish,
  onToggleVoice,
  onCancel,
  onSubmit,
}: ChatInputActionsRowProps) {
  const { t } = useTranslation();
  const actionsRowRef = useRef<HTMLDivElement | null>(null);
  const [isCompact, setIsCompact] = useState(false);
  const [skillPickerOpen, setSkillPickerOpen] = useState(false);
  const [expertPickerOpen, setExpertPickerOpen] = useState(false);
  const [connectorPickerOpen, setConnectorPickerOpen] = useState(false);
  const [knowledgePickerOpen, setKnowledgePickerOpen] = useState(false);
  const [shortcutOpen, setShortcutOpen] = useState(false);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [reasoningModelRef, setReasoningModelRef] = useState<string | null>(
    null,
  );
  /** Mobile-only bottom drawer for the overflow ("more") menu. */
  const [mobileOverflowOpen, setMobileOverflowOpen] = useState(false);
  /** Narrow-desktop overflow popover (tools / skills / …). */
  const [overflowPopoverOpen, setOverflowPopoverOpen] = useState(false);
  /** Active sub-picker for compact layouts (drawer on mobile, panel in popover). */
  const [compactPicker, setCompactPicker] = useState<CompactPickerKey | null>(
    null,
  );

  const modelOverride = resolveTurnModelOverride(selectedModel, defaultModel);
  const useCompactControls = isMobile || isCompact;

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
  const effectiveModelRef = selectedModel || defaultModel || "";
  const selectedModelInfo = availableModels?.find(
    (model) => modelOptionValue(model) === effectiveModelRef,
  );
  const reasoningCapability = selectedModelInfo?.reasoning_config;
  const reasoningIsStatusOnly = reasoningCapability?.adapter === "status_only";
  const showConnectorPicker = Boolean(
    availableConnectors && onConnectorsChange,
  );
  const showKnowledgePicker = Boolean(
    availableKnowledgeBases && onKnowledgeBaseIdsChange,
  );
  const showSkillPicker = Boolean(availableSkills && onSkillsChange);
  const showExpertPicker = Boolean(
    availableExperts && onTargetAgentsChange && availableExperts.length > 0,
  );
  const showShortcutPicker = true;
  const showOverflowMenu =
    showConnectorPicker ||
    showKnowledgePicker ||
    showSkillPicker ||
    showExpertPicker ||
    showShortcutPicker;

  const overflowBadgeCount =
    selectedConnectors.length +
    selectedKnowledgeBaseIds.length +
    selectedSkills.length +
    selectedTargetAgents.length;

  const closeCompactPicker = () => {
    setCompactPicker(null);
    setReasoningModelRef(null);
  };

  const openCompactPicker = (key: CompactPickerKey) => {
    if (isMobile) setMobileOverflowOpen(false);
    setCompactPicker(key);
  };

  const compactPickerTitle: Record<CompactPickerKey, string> = {
    model: t("chat.selectModel", "Select model"),
    connector: t("connectors.chatPicker"),
    knowledge: t("chat.knowledgePicker"),
    skill: t("chat.skillPicker"),
    expert: t("chat.expertPicker"),
    shortcut: t("shortcut.title", "快捷指令"),
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
        {useCompactControls && (
          <button
            type="button"
            className={styles.reasoningMenuBack}
            onClick={() => setReasoningModelRef(null)}
            aria-label={t("common.back", "返回")}
          >
            <ChevronLeft size={16} />
          </button>
        )}
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
    <div
      className={`${styles.modelPickerPanel} ${
        reasoningMenu ? styles.modelPickerPanelExpanded : ""
      }`}
    >
      {(!useCompactControls || !reasoningMenu) && (
        <div className={styles.modelMenu}>
          <button
            type="button"
            className={`${styles.modelMenuItem} ${
              !selectedModel ? styles.modelMenuItemActive : ""
            }`}
            onClick={() => {
              onModelChange?.(null);
              closeCompactPicker();
              setModelPickerOpen(false);
            }}
          >
            <span className={styles.modelMenuLabel}>
              {t("chat.modelAuto", "Auto")}
            </span>
            <span className={styles.modelMenuHint}>
              {t("chat.modelAutoHint", "Use agent default")}
            </span>
          </button>
          {availableModels?.map((model) => {
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
                    closeCompactPicker();
                    setModelPickerOpen(false);
                  }}
                >
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
            closeCompactPicker();
            onSlashShortcutSelect(command);
          }}
          onHover={() => undefined}
        />
      </div>
    </div>
  );

  const renderMobileOverflowMenu = () => (
    <div className={styles.mobileOverflowMenu}>
      {showConnectorPicker && (
        <button
          type="button"
          className={styles.mobileOverflowItem}
          onClick={() => openCompactPicker("connector")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <Link2 size={18} />
            <span>{t("connectors.chatPicker")}</span>
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            {selectedConnectors.length > 0 && (
              <span className={styles.toolbarBadge}>
                {selectedConnectors.length}
              </span>
            )}
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showKnowledgePicker && (
        <button
          type="button"
          className={styles.mobileOverflowItem}
          onClick={() => openCompactPicker("knowledge")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <BookOpen size={18} />
            <span>{t("chat.knowledgePicker")}</span>
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            {selectedKnowledgeBaseIds.length > 0 && (
              <span className={styles.toolbarBadge}>
                {selectedKnowledgeBaseIds.length}
              </span>
            )}
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showSkillPicker && (
        <button
          type="button"
          className={styles.mobileOverflowItem}
          onClick={() => openCompactPicker("skill")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <Sparkles size={18} />
            <span>{t("chat.skillPicker")}</span>
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            {selectedSkills.length > 0 && (
              <span
                className={`${styles.toolbarBadge} ${styles.toolbarBadgeSkill}`}
              >
                {selectedSkills.length}
              </span>
            )}
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showExpertPicker && (
        <button
          type="button"
          className={styles.mobileOverflowItem}
          onClick={() => openCompactPicker("expert")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <GraduationCap size={18} />
            <span>{t("chat.expertPicker")}</span>
          </span>
          <span className={styles.mobileOverflowItemMeta}>
            {selectedTargetAgents.length > 0 && (
              <span
                className={`${styles.toolbarBadge} ${styles.toolbarBadgeExpert}`}
              >
                {selectedTargetAgents.length}
              </span>
            )}
            <ChevronRight size={16} />
          </span>
        </button>
      )}
      {showShortcutPicker && (
        <button
          type="button"
          className={styles.mobileOverflowItem}
          onClick={() => openCompactPicker("shortcut")}
        >
          <span className={styles.mobileOverflowItemMain}>
            <Zap size={18} />
            <span>{t("shortcut.title", "快捷指令")}</span>
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
      case "model":
        return modelMenu;
      case "connector":
        return (
          <ConnectorPickerPopover
            connectors={availableConnectors ?? []}
            selectedConnectors={selectedConnectors}
            onConnectorsChange={onConnectorsChange!}
            onNavigateAway={closeCompactPicker}
          />
        );
      case "knowledge":
        return (
          <KnowledgePickerPopover
            knowledgeBases={availableKnowledgeBases ?? []}
            selectedKnowledgeBaseIds={selectedKnowledgeBaseIds}
            onKnowledgeBaseIdsChange={onKnowledgeBaseIdsChange!}
            onNavigateAway={closeCompactPicker}
          />
        );
      case "skill":
        return (
          <SkillPickerPopover
            skills={availableSkills ?? []}
            selectedSkills={selectedSkills}
            onSkillsChange={onSkillsChange!}
            onNavigateAway={closeCompactPicker}
          />
        );
      case "expert":
        return (
          <ExpertPickerPopover
            agents={availableExperts ?? []}
            selectedAgentIds={selectedTargetAgents}
            onAgentsChange={onTargetAgentsChange!}
            onNavigateAway={closeCompactPicker}
          />
        );
      case "shortcut":
        return shortcutMenu;
      default:
        return null;
    }
  };

  const compactPickerContent = compactPicker ? (
    <div className={styles.compactPickerPanel}>
      <button
        type="button"
        className={styles.compactPickerBack}
        onClick={closeCompactPicker}
      >
        <ChevronLeft size={16} />
        <span>{compactPickerTitle[compactPicker]}</span>
      </button>
      {renderCompactPickerContent()}
    </div>
  ) : (
    renderMobileOverflowMenu()
  );

  const renderSecondaryActions = () => {
    if (useCompactControls) {
      const modelButton = (
        <button
          className={`${styles.secondaryBtn} ${
            modelOverride || reasoningMode !== "auto" || reasoningEffort
              ? styles.secondaryBtnModelActive
              : ""
          }`}
          type="button"
          onClick={isMobile ? () => setCompactPicker("model") : undefined}
        >
          <Cpu size={16} />
        </button>
      );
      const overflowButton = (
        <button
          className={`${styles.secondaryBtn} ${
            overflowBadgeCount > 0 ? styles.secondaryBtnActive : ""
          }`}
          type="button"
          onClick={isMobile ? () => setMobileOverflowOpen(true) : undefined}
        >
          <MoreHorizontal size={16} />
          {overflowBadgeCount > 0 && (
            <span className={styles.toolbarBadge}>{overflowBadgeCount}</span>
          )}
        </button>
      );

      return (
        <>
          {showModelPicker &&
            (isMobile ? (
              modelButton
            ) : (
              <Popover
                trigger="click"
                placement="topLeft"
                open={modelPickerOpen}
                onOpenChange={(open) => {
                  setModelPickerOpen(open);
                  if (open) setOverflowPopoverOpen(false);
                  if (!open) setReasoningModelRef(null);
                }}
                overlayClassName={styles.modelPopover}
                content={modelMenu}
              >
                {modelButton}
              </Popover>
            ))}
          <button
            className={styles.secondaryBtn}
            onClick={onFileSelect}
            type="button"
            disabled={uploading}
          >
            <Paperclip size={16} />
          </button>
          {showOverflowMenu &&
            (isMobile ? (
              overflowButton
            ) : (
              <Popover
                trigger="click"
                placement="topLeft"
                open={overflowPopoverOpen}
                overlayClassName={styles.skillPickerPopover}
                content={compactPickerContent}
                onOpenChange={(open) => {
                  setOverflowPopoverOpen(open);
                  if (open) {
                    setModelPickerOpen(false);
                    setCompactPicker(null);
                    setReasoningModelRef(null);
                  } else {
                    closeCompactPicker();
                  }
                }}
              >
                {overflowButton}
              </Popover>
            ))}
          {isMobile && (
            <>
              <Drawer
                open={mobileOverflowOpen}
                onClose={() => setMobileOverflowOpen(false)}
                placement="bottom"
                height="auto"
                title={t("chat.composerMore", "更多工具")}
                className={styles.mobilePickerDrawer}
                styles={{ body: { padding: 0 } }}
                destroyOnHidden
              >
                {renderMobileOverflowMenu()}
              </Drawer>
              <Drawer
                open={compactPicker !== null}
                onClose={closeCompactPicker}
                placement="bottom"
                height="auto"
                title={compactPicker ? compactPickerTitle[compactPicker] : ""}
                className={styles.mobilePickerDrawer}
                styles={{ body: { padding: 0 } }}
                destroyOnHidden
              >
                {renderCompactPickerContent()}
              </Drawer>
            </>
          )}
        </>
      );
    }

    return (
      <>
        {showModelPicker && (
          <Popover
            trigger="click"
            placement="topLeft"
            open={modelPickerOpen}
            onOpenChange={(open) => {
              setModelPickerOpen(open);
              if (!open) setReasoningModelRef(null);
            }}
            overlayClassName={styles.modelPopover}
            content={modelMenu}
          >
            <Tooltip
              title={
                selectedModel
                  ? modelOptionLabel(
                      availableModels!.find(
                        (m) => modelOptionValue(m) === selectedModel,
                      ) ?? {
                        provider_name: selectedModel.split("/")[0] || "",
                        model:
                          selectedModel.split("/").slice(1).join("/") ||
                          selectedModel,
                      },
                    )
                  : t("chat.selectModel", "Select model")
              }
              mouseEnterDelay={0.4}
            >
              <button
                className={`${styles.secondaryBtn} ${styles.modelPickerBtn} ${
                  modelOverride || reasoningMode !== "auto" || reasoningEffort
                    ? styles.secondaryBtnModelActive
                    : ""
                }`}
                type="button"
              >
                <Cpu size={16} />
                <span className={styles.modelPickerLabel}>
                  {selectedModel
                    ? modelShortLabel(selectedModel)
                    : t("chat.modelAuto", "Auto")}
                  {selectedModel && reasoningCapability && (
                    <span className={styles.modelPickerReasoningLabel}>
                      {` · ${
                        reasoningIsStatusOnly
                          ? t("chat.reasoningAlways", "始终推理")
                          : reasoningEffort || reasoningModeLabel(reasoningMode)
                      }`}
                    </span>
                  )}
                </span>
              </button>
            </Tooltip>
          </Popover>
        )}
        {showConnectorPicker && (
          <Popover
            trigger="click"
            placement="topLeft"
            open={connectorPickerOpen}
            onOpenChange={setConnectorPickerOpen}
            overlayClassName={styles.skillPickerPopover}
            content={
              <ConnectorPickerPopover
                connectors={availableConnectors!}
                selectedConnectors={selectedConnectors}
                onConnectorsChange={onConnectorsChange!}
                onNavigateAway={() => setConnectorPickerOpen(false)}
              />
            }
          >
            <Tooltip title={t("connectors.chatPicker")} mouseEnterDelay={0.4}>
              <button
                className={`${styles.secondaryBtn} ${
                  selectedConnectors.length > 0 ? styles.secondaryBtnActive : ""
                }`}
                type="button"
              >
                <Link2 size={16} />
                {selectedConnectors.length > 0 && (
                  <span className={styles.toolbarBadge}>
                    {selectedConnectors.length}
                  </span>
                )}
              </button>
            </Tooltip>
          </Popover>
        )}
        {showKnowledgePicker && (
          <Popover
            trigger="click"
            placement="topLeft"
            open={knowledgePickerOpen}
            onOpenChange={setKnowledgePickerOpen}
            overlayClassName={styles.skillPickerPopover}
            content={
              <KnowledgePickerPopover
                knowledgeBases={availableKnowledgeBases!}
                selectedKnowledgeBaseIds={selectedKnowledgeBaseIds}
                onKnowledgeBaseIdsChange={onKnowledgeBaseIdsChange!}
                onNavigateAway={() => setKnowledgePickerOpen(false)}
              />
            }
          >
            <Tooltip title={t("chat.knowledgePicker")} mouseEnterDelay={0.4}>
              <button
                className={`${styles.secondaryBtn} ${
                  selectedKnowledgeBaseIds.length > 0
                    ? styles.secondaryBtnActive
                    : ""
                }`}
                type="button"
              >
                <BookOpen size={16} />
                {selectedKnowledgeBaseIds.length > 0 && (
                  <span className={styles.toolbarBadge}>
                    {selectedKnowledgeBaseIds.length}
                  </span>
                )}
              </button>
            </Tooltip>
          </Popover>
        )}
        {showSkillPicker && (
          <Popover
            trigger="click"
            placement="topLeft"
            open={skillPickerOpen}
            onOpenChange={setSkillPickerOpen}
            overlayClassName={styles.skillPickerPopover}
            content={
              <SkillPickerPopover
                skills={availableSkills!}
                selectedSkills={selectedSkills}
                onSkillsChange={onSkillsChange!}
                onNavigateAway={() => setSkillPickerOpen(false)}
              />
            }
          >
            <Tooltip title={t("chat.skillPicker")} mouseEnterDelay={0.4}>
              <button
                className={`${styles.secondaryBtn} ${
                  selectedSkills.length > 0
                    ? styles.secondaryBtnSkillActive
                    : ""
                }`}
                type="button"
              >
                <Sparkles size={16} />
                {selectedSkills.length > 0 && (
                  <span
                    className={`${styles.toolbarBadge} ${styles.toolbarBadgeSkill}`}
                  >
                    {selectedSkills.length}
                  </span>
                )}
              </button>
            </Tooltip>
          </Popover>
        )}
        {showExpertPicker && (
          <Popover
            trigger="click"
            placement="topLeft"
            open={expertPickerOpen}
            onOpenChange={setExpertPickerOpen}
            overlayClassName={styles.skillPickerPopover}
            content={
              <ExpertPickerPopover
                agents={availableExperts!}
                selectedAgentIds={selectedTargetAgents}
                onAgentsChange={onTargetAgentsChange!}
                onNavigateAway={() => setExpertPickerOpen(false)}
              />
            }
          >
            <Tooltip title={t("chat.expertPicker")} mouseEnterDelay={0.4}>
              <button
                className={`${styles.secondaryBtn} ${
                  selectedTargetAgents.length > 0
                    ? styles.secondaryBtnExpertActive
                    : ""
                }`}
                type="button"
              >
                <GraduationCap size={16} />
                {selectedTargetAgents.length > 0 && (
                  <span
                    className={`${styles.toolbarBadge} ${styles.toolbarBadgeExpert}`}
                  >
                    {selectedTargetAgents.length}
                  </span>
                )}
              </button>
            </Tooltip>
          </Popover>
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
            <button className={styles.secondaryBtn} type="button">
              <Zap size={16} />
            </button>
          </Tooltip>
        </Popover>
        <Tooltip
          title={t("upload.fileTooltip", "Upload attachment")}
          mouseEnterDelay={0.4}
        >
          <button
            className={styles.secondaryBtn}
            onClick={onFileSelect}
            type="button"
            disabled={uploading}
          >
            <Paperclip size={16} />
          </button>
        </Tooltip>
      </>
    );
  };

  return (
    <div ref={actionsRowRef} className={styles.actionsRow}>
      <div className={styles.secondaryActions}>{renderSecondaryActions()}</div>
      <div className={styles.inputActions}>
        <ContextWindowRing
          usedTokens={contextUsedTokens}
          maxTokens={contextMaxTokens}
          agentId={agentId}
          threadId={threadId}
          selectedConnectors={selectedConnectors}
          selectedSkills={selectedSkills}
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
            disabled={disabled || isStreaming || transcribing || !_sttAvailable}
            onClick={onToggleVoice}
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
            <Tooltip title={t("chat.stop", "Stop")} mouseEnterDelay={0.4}>
              <button
                className={`${styles.sendBtn} ${styles.cancelBtn}`}
                onClick={onCancel}
                title={t("chat.stop", "Stop")}
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
