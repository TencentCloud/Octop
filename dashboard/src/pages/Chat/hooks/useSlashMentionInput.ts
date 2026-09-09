import { useCallback, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import type { SlashCommandSpec } from "../../../api/modules/slash";
import { resolveSlashIcon } from "../../../utils/slashIcons";
import { groupSlashByCategory } from "../../../utils/slashCategories";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import type { ChatAgentOption } from "../components/ExpertAgentAvatar";
import type { AgentSubagentSummary } from "../../../api/modules/subagents";
import {
  buildMentionItems,
  type MentionPick,
} from "../components/MentionPickerMenu";
import { getMentionAtCursor } from "../utils/mentionAtCursor";
import { isSlashNamePrefix } from "../utils/slashText";
import {
  slashCommandNeedsInput,
  slashCommandPrefillText,
} from "../../../utils/quickInputPrefill";
import { replaceMentionQuery } from "../utils/expertMention";

export type SlashMenuItem = {
  command: string;
  label: string;
  icon: ReturnType<typeof resolveSlashIcon>;
  tone: string;
  spec: SlashCommandSpec;
};

interface UseSlashMentionInputParams {
  text: string;
  setText: (value: string) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  slashCommands: SlashCommandSpec[];
  labelFor: (spec: SlashCommandSpec) => string;
  locale: string;
  availableSkills?: SkillSpec[];
  availableConnectors?: {
    mcp_server_name: string;
    label: string;
    kind: string;
  }[];
  /**
   * Subset of experts the user can currently pick — already filtered by the
   * caller (only running experts). The hook itself doesn't filter further.
   */
  availableExperts: ChatAgentOption[];
  availableSubagents?: AgentSubagentSummary[];
  agentId?: string | null;
  selectedConnectors: string[];
  onConnectorsChange?: (names: string[]) => void;
  onSend: (text: string) => void;
  onNewChat: () => void;
  onCancel: () => void;
  isStreaming: boolean;
  onSubmitRef: React.MutableRefObject<() => void>;
  /** When false, Enter inserts a newline; send only via button (mobile). */
  enterToSend?: boolean;
}

export function useSlashMentionInput({
  text,
  setText,
  textareaRef,
  slashCommands,
  labelFor,
  locale,
  availableSkills,
  availableConnectors,
  availableExperts,
  availableSubagents = [],
  agentId,
  selectedConnectors,
  onConnectorsChange,
  onSend,
  onNewChat,
  onCancel,
  isStreaming: _isStreaming,
  onSubmitRef,
  enterToSend = true,
}: UseSlashMentionInputParams) {
  const [slashMenuOpen, setSlashMenuOpen] = useState(false);
  const [slashMenuIndex, setSlashMenuIndex] = useState(0);
  const [mentionMenuOpen, setMentionMenuOpen] = useState(false);
  const [mentionMenuIndex, setMentionMenuIndex] = useState(0);
  const [mentionQuery, setMentionQuery] = useState("");
  const [mentionAtIndex, setMentionAtIndex] = useState(-1);

  const mentionAgents = useMemo(
    () => availableExperts.filter((a) => a.agent_id !== agentId),
    [availableExperts, agentId],
  );

  const mentionItems = useMemo(
    () =>
      buildMentionItems(
        mentionQuery,
        availableConnectors ?? [],
        mentionAgents,
        availableSubagents,
      ),
    [mentionQuery, availableConnectors, mentionAgents, availableSubagents],
  );

  const reservedSlashNames = useMemo(() => {
    const names = new Set<string>();
    for (const spec of slashCommands) {
      names.add(spec.name);
      for (const alias of spec.aliases) names.add(alias);
    }
    return names;
  }, [slashCommands]);

  const slashMenuItems = useMemo<SlashMenuItem[]>(() => {
    const commands = slashCommands.map((spec) => ({
      command: spec.usage || `/${spec.name}`,
      label: labelFor(spec),
      icon: resolveSlashIcon(spec.icon),
      tone: spec.tone,
      spec,
    }));
    const skills = (availableSkills ?? [])
      .filter((skill) => skill.enabled && !reservedSlashNames.has(skill.slug))
      .map((skill) => {
        const command = `/${skill.slug}`;
        return {
          command,
          label: skill.name || skill.slug,
          icon: resolveSlashIcon("Sparkles"),
          tone: "violet",
          spec: {
            name: skill.slug,
            command,
            aliases: [],
            label_en: skill.name || skill.slug,
            label_zh: skill.name || skill.slug,
            description_en: skill.description || "",
            description_zh: skill.description || "",
            usage: `${command} <task>`,
            icon: "Sparkles",
            tone: "violet",
            category: "skills",
            origins: ["ui"],
            client_action: "none" as const,
          },
        };
      });
    return [...commands, ...skills];
  }, [slashCommands, labelFor, availableSkills, reservedSlashNames]);

  const filteredSlashCommands = useMemo(() => {
    if (!slashMenuOpen) return slashMenuItems;
    const query = text.slice(1).toLowerCase();
    if (!query) return slashMenuItems;
    return slashMenuItems.filter(
      (c) =>
        c.command.toLowerCase().includes(query) ||
        c.label.toLowerCase().includes(query) ||
        c.spec.name.includes(query),
    );
  }, [text, slashMenuOpen, slashMenuItems]);

  const slashMenuQuery = text.startsWith("/")
    ? text.slice(1).toLowerCase()
    : "";
  const slashMenuGrouped = slashMenuOpen && !slashMenuQuery;

  const slashMenuGroups = useMemo(
    () =>
      slashMenuGrouped
        ? groupSlashByCategory(filteredSlashCommands, locale)
        : null,
    [slashMenuGrouped, filteredSlashCommands, locale],
  );

  const slashMenuFlat = useMemo(
    () =>
      slashMenuGroups
        ? slashMenuGroups.flatMap((group) => group.items)
        : filteredSlashCommands,
    [slashMenuGroups, filteredSlashCommands],
  );

  const slashPickerGroups = useMemo(
    () => groupSlashByCategory(slashMenuItems, locale),
    [slashMenuItems, locale],
  );

  const focusTextareaEnd = useCallback(() => {
    setTimeout(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    }, 0);
  }, [textareaRef]);

  const runSlashCommand = useCallback(
    (item: SlashMenuItem) => {
      setSlashMenuOpen(false);
      if (item.spec.client_action === "new_chat") {
        onNewChat();
        setText("");
      } else if (item.spec.client_action === "cancel_stream") {
        onCancel();
        setText("");
      } else if (slashCommandNeedsInput(item.spec)) {
        setText(slashCommandPrefillText(item.spec));
        focusTextareaEnd();
      } else {
        onSend(item.command);
        setText("");
      }
    },
    [onSend, onNewChat, onCancel, setText, focusTextareaEnd],
  );

  const matchSlashCommand = useCallback(
    (trimmed: string): SlashMenuItem | undefined =>
      slashMenuItems.find(
        (c) =>
          c.command === trimmed ||
          `/${c.spec.name}` === trimmed ||
          c.spec.aliases.some((a) => `/${a}` === trimmed),
      ),
    [slashMenuItems],
  );

  const focusAt = useCallback(
    (cursor: number) => {
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(cursor, cursor);
      });
    },
    [textareaRef],
  );

  const handleMentionSelect = useCallback(
    (pick: MentionPick) => {
      setMentionMenuOpen(false);
      if (pick.kind === "agent" || pick.kind === "subagent") {
        const tokenName = pick.kind === "subagent" ? pick.slug : pick.label;
        const next = replaceMentionQuery(
          text,
          mentionAtIndex,
          mentionQuery,
          tokenName,
        );
        setText(next.text);
        focusAt(next.cursor);
        return;
      }
      const before = text.slice(0, mentionAtIndex);
      const after = text.slice(mentionAtIndex + mentionQuery.length + 1);
      setText(`${before}${after}`.trimStart());
      if (pick.kind === "connector" && onConnectorsChange) {
        onConnectorsChange(
          selectedConnectors.includes(pick.name)
            ? selectedConnectors.filter((n) => n !== pick.name)
            : [...selectedConnectors, pick.name],
        );
      }
      textareaRef.current?.focus();
    },
    [
      text,
      mentionAtIndex,
      mentionQuery,
      setText,
      onConnectorsChange,
      selectedConnectors,
      textareaRef,
      focusAt,
    ],
  );

  const handleSlashSelect = useCallback(
    (command: string) => {
      const item = slashMenuItems.find((c) => c.command === command);
      if (item) runSlashCommand(item);
    },
    [slashMenuItems, runSlashCommand],
  );

  const handleTextChange = useCallback(
    (val: string) => {
      setText(val);
      if (isSlashNamePrefix(val)) {
        setSlashMenuOpen(true);
        setSlashMenuIndex(0);
        setMentionMenuOpen(false);
      } else {
        setSlashMenuOpen(false);
        const mention = getMentionAtCursor(val);
        if (
          mention &&
          (availableConnectors ||
            mentionAgents.length > 0 ||
            availableSubagents.length > 0)
        ) {
          setMentionMenuOpen(true);
          setMentionQuery(mention.query);
          setMentionAtIndex(mention.atIndex);
          setMentionMenuIndex(0);
        } else {
          setMentionMenuOpen(false);
        }
      }
    },
    [
      setText,
      availableConnectors,
      mentionAgents.length,
      availableSubagents.length,
    ],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.nativeEvent.isComposing || e.keyCode === 229) return;

      if (mentionMenuOpen && mentionItems.length > 0) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setMentionMenuIndex((i) => (i + 1) % mentionItems.length);
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          setMentionMenuIndex(
            (i) => (i - 1 + mentionItems.length) % mentionItems.length,
          );
          return;
        }
        if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
          e.preventDefault();
          const selected = mentionItems[mentionMenuIndex];
          if (selected) handleMentionSelect(selected);
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setMentionMenuOpen(false);
          return;
        }
      }

      if (slashMenuOpen && slashMenuFlat.length > 0) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setSlashMenuIndex((i) => (i + 1) % slashMenuFlat.length);
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          setSlashMenuIndex(
            (i) => (i - 1 + slashMenuFlat.length) % slashMenuFlat.length,
          );
          return;
        }
        if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
          e.preventDefault();
          const selected = slashMenuFlat[slashMenuIndex];
          if (selected) handleSlashSelect(selected.command);
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setSlashMenuOpen(false);
          return;
        }
      }

      if (enterToSend && e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        // During streaming, submit queues the message instead of sending.
        onSubmitRef.current();
      }
    },
    [
      enterToSend,
      onSubmitRef,
      mentionMenuOpen,
      mentionItems,
      mentionMenuIndex,
      handleMentionSelect,
      slashMenuOpen,
      slashMenuFlat,
      slashMenuIndex,
      handleSlashSelect,
    ],
  );

  const closeShortcutPicker = useCallback(() => {
    setSlashMenuOpen(false);
  }, []);

  return {
    slashMenuOpen,
    slashMenuIndex,
    setSlashMenuIndex,
    mentionMenuOpen,
    mentionMenuIndex,
    setMentionMenuIndex,
    mentionQuery,
    mentionAgents,
    slashMenuFlat,
    slashMenuGroups,
    slashPickerGroups,
    slashMenuItems,
    mentionItems,
    runSlashCommand,
    matchSlashCommand,
    handleMentionSelect,
    handleSlashSelect,
    handleTextChange,
    handleKeyDown,
    closeShortcutPicker,
  };
}
