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
  GraduationCap,
  MoreHorizontal,
  ChevronRight,
} from "lucide-react";
import { Tooltip, Popover, Drawer } from "antd";
import type { ResolvedModel } from "../../../api/types";
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
import SlashCommandMenu from "./SlashCommandMenu";
import type { SlashMenuGroup } from "../../../utils/slashCategories";
import type { SlashMenuItem } from "../hooks/useSlashMentionInput";
import { SHORTCUT_ICON_TONE_CLASS } from "../utils/slashShortcutStyles";
import { isSttAvailable } from "../../../hooks/useVoiceInput";
import { resolveTurnModelOverride } from "../utils/chatMessages";
import styles from "../index.module.less";

type MobilePickerKey = "model" | "connector" | "skill" | "expert" | "shortcut";

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
  availableConnectors?: {
    mcp_server_name: string;
    label: string;
    kind: string;
  }[];
  selectedConnectors?: string[];
  onConnectorsChange?: (names: string[]) => void;
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
  availableConnectors,
  selectedConnectors = [],
  onConnectorsChange,
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
  const [shortcutOpen, setShortcutOpen] = useState(false);
  const [mobileOverflowOpen, setMobileOverflowOpen] = useState(false);
  const [mobilePicker, setMobilePicker] = useState<MobilePickerKey | null>(
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
  const showConnectorPicker = Boolean(
    availableConnectors && onConnectorsChange,
  );
  const showSkillPicker = Boolean(availableSkills && onSkillsChange);
  const showExpertPicker = Boolean(
    availableExperts && onTargetAgentsChange && availableExperts.length > 0,
  );
  const showShortcutPicker = true;
  const showOverflowMenu =
    showConnectorPicker ||
    showSkillPicker ||
    showExpertPicker ||
    showShortcutPicker;

  const overflowBadgeCount =
    selectedConnectors.length +
    selectedSkills.length +
    selectedTargetAgents.length;

  const closeMobilePicker = () => setMobilePicker(null);

  const openMobilePicker = (key: MobilePickerKey) => {
    setMobileOverflowOpen(false);
    setMobilePicker(key);
  };

  const mobilePickerTitle: Record<MobilePickerKey, string> = {
    model: t("chat.selectModel", "Select model"),
    connector: t("connectors.chatPicker"),
    skill: t("chat.skillPicker"),
    expert: t("chat.expertPicker"),
    shortcut: t("shortcut.title", "快捷指令"),
  };

  const modelMenu = (
    <div className={styles.modelMenu}>
      <button
        type="button"
        className={`${styles.modelMenuItem} ${
          !selectedModel ? styles.modelMenuItemActive : ""
        }`}
        onClick={() => {
          onModelChange?.(null);
          closeMobilePicker();
        }}
      >
        <span className={styles.modelMenuLabel}>
          {t("chat.modelAuto", "Auto")}
        </span>
        <span className={styles.modelMenuHint}>
          {t("chat.modelAutoHint", "Use agent default")}
        </span>
      </button>
      {availableModels?.map((m) => {
        const value = modelOptionValue(m);
        const active = selectedModel === value;
        return (
          <button
            key={value}
            type="button"
            className={`${styles.modelMenuItem} ${
              active ? styles.modelMenuItemActive : ""
            }`}
            onClick={() => {
              onModelChange?.(active ? null : value);
              closeMobilePicker();
            }}
          >
            <span className={styles.modelMenuLabel}>{modelOptionLabel(m)}</span>
          </button>
        );
      })}
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
            closeMobilePicker();
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
          onClick={() => openMobilePicker("connector")}
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
      {showSkillPicker && (
        <button
          type="button"
          className={styles.mobileOverflowItem}
          onClick={() => openMobilePicker("skill")}
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
          onClick={() => openMobilePicker("expert")}
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
          onClick={() => openMobilePicker("shortcut")}
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

  const renderMobilePickerContent = () => {
    switch (mobilePicker) {
      case "model":
        return modelMenu;
      case "connector":
        return (
          <ConnectorPickerPopover
            connectors={availableConnectors ?? []}
            selectedConnectors={selectedConnectors}
            onConnectorsChange={onConnectorsChange!}
            onNavigateAway={closeMobilePicker}
          />
        );
      case "skill":
        return (
          <SkillPickerPopover
            skills={availableSkills ?? []}
            selectedSkills={selectedSkills}
            onSkillsChange={onSkillsChange!}
            onNavigateAway={closeMobilePicker}
          />
        );
      case "expert":
        return (
          <ExpertPickerPopover
            agents={availableExperts ?? []}
            selectedAgentIds={selectedTargetAgents}
            onAgentsChange={onTargetAgentsChange!}
            onNavigateAway={closeMobilePicker}
          />
        );
      case "shortcut":
        return shortcutMenu;
      default:
        return null;
    }
  };

  const renderSecondaryActions = () => {
    if (useCompactControls) {
      return (
        <>
          {showModelPicker && (
            <button
              className={`${styles.secondaryBtn} ${
                modelOverride ? styles.secondaryBtnModelActive : ""
              }`}
              type="button"
              onClick={() => setMobilePicker("model")}
            >
              <Cpu size={16} />
            </button>
          )}
          <button
            className={styles.secondaryBtn}
            onClick={onFileSelect}
            type="button"
            disabled={uploading}
          >
            <Paperclip size={16} />
          </button>
          {showOverflowMenu && (
            <button
              className={`${styles.secondaryBtn} ${
                overflowBadgeCount > 0 ? styles.secondaryBtnActive : ""
              }`}
              type="button"
              onClick={() => setMobileOverflowOpen(true)}
            >
              <MoreHorizontal size={16} />
              {overflowBadgeCount > 0 && (
                <span className={styles.toolbarBadge}>
                  {overflowBadgeCount}
                </span>
              )}
            </button>
          )}
          <Drawer
            open={mobileOverflowOpen}
            onClose={() => setMobileOverflowOpen(false)}
            placement="bottom"
            height="auto"
            title={t("chat.composerMore", "更多工具")}
            className={styles.mobilePickerDrawer}
            styles={{ body: { padding: 0 } }}
            destroyOnClose
          >
            {renderMobileOverflowMenu()}
          </Drawer>
          <Drawer
            open={mobilePicker !== null}
            onClose={closeMobilePicker}
            placement="bottom"
            height="auto"
            title={mobilePicker ? mobilePickerTitle[mobilePicker] : ""}
            className={styles.mobilePickerDrawer}
            styles={{ body: { padding: 0 } }}
            destroyOnClose
          >
            {renderMobilePickerContent()}
          </Drawer>
        </>
      );
    }

    return (
      <>
        {showModelPicker && (
          <Popover
            trigger="click"
            placement="topLeft"
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
                  modelOverride ? styles.secondaryBtnModelActive : ""
                }`}
                type="button"
              >
                <Cpu size={16} />
                <span className={styles.modelPickerLabel}>
                  {selectedModel
                    ? modelShortLabel(selectedModel)
                    : t("chat.modelAuto", "Auto")}
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
          <button
            className={`${styles.sendBtn} ${styles.cancelBtn}`}
            onClick={onCancel}
            title="Stop"
            type="button"
          >
            <Square size={18} />
          </button>
        ) : (
          <button
            className={styles.sendBtn}
            onClick={onSubmit}
            disabled={!canSend}
            title="Send"
            type="button"
          >
            <Send size={18} />
          </button>
        )}
      </div>
    </div>
  );
}
