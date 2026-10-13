import { useTranslation } from "react-i18next";
import { FileText, Plug } from "lucide-react";
import type { ChatConnectorOption } from "./ConnectorPickerPopover";
import type { ChatAgentOption } from "./ExpertAgentAvatar";
import type { AgentSubagentSummary } from "../../../api/modules/subagents";
import {
  isPathLikeMentionQuery,
  workspaceMentionHintState,
  type WorkspaceMentionFile,
  type WorkspaceMentionHint,
} from "../utils/fileMention";
import ExpertAgentAvatar from "./ExpertAgentAvatar";
import styles from "../index.module.less";

export type MentionAgentOption = ChatAgentOption;

export type MentionPick =
  | { kind: "connector"; name: string; label: string }
  | { kind: "agent"; agent_id: string; label: string }
  | { kind: "subagent"; slug: string; label: string }
  | { kind: "file"; path: string; label: string };

export function mentionPickKey(item: MentionPick): string {
  if (item.kind === "file") return `file:${item.path}`;
  if (item.kind === "subagent") return `subagent:${item.slug}`;
  if (item.kind === "connector") return `connector:${item.name}`;
  return `agent:${item.agent_id}`;
}

export function firstFileMentionIndex(items: MentionPick[]): number {
  return items.findIndex((item) => item.kind === "file");
}

export function buildMentionItems(
  query: string,
  connectors: ChatConnectorOption[],
  agents: MentionAgentOption[] = [],
  subagents: AgentSubagentSummary[] = [],
  files: WorkspaceMentionFile[] = [],
  options: { filesFirst?: boolean } = {},
): MentionPick[] {
  const q = query.trim().toLowerCase();
  const people: MentionPick[] = [];
  for (const c of connectors) {
    if (
      q &&
      !c.label.toLowerCase().includes(q) &&
      !c.mcp_server_name.toLowerCase().includes(q)
    ) {
      continue;
    }
    people.push({ kind: "connector", name: c.mcp_server_name, label: c.label });
  }
  for (const a of agents) {
    if (
      q &&
      !a.name.toLowerCase().includes(q) &&
      !a.agent_id.toLowerCase().includes(q)
    )
      continue;
    people.push({ kind: "agent", agent_id: a.agent_id, label: a.name });
  }
  for (const s of subagents) {
    const label = s.name || s.slug;
    if (
      q &&
      !label.toLowerCase().includes(q) &&
      !s.slug.toLowerCase().includes(q)
    ) {
      continue;
    }
    people.push({ kind: "subagent", slug: s.slug, label });
  }

  const filePicks: MentionPick[] = [];
  if (q) {
    for (const file of files) {
      filePicks.push({ kind: "file", path: file.path, label: file.label });
    }
  }

  const filesFirst = options.filesFirst ?? isPathLikeMentionQuery(query);
  return filesFirst ? [...filePicks, ...people] : [...people, ...filePicks];
}

const HINT_KEYS: Record<WorkspaceMentionHint, string> = {
  searching: "mention.searching",
  need_agent: "mention.filesNeedAgent",
  failed: "mention.filesFailed",
  typeToSearch: "mention.typeToSearch",
  typeMore: "mention.typeMore",
  filesEmpty: "mention.filesEmpty",
};

const HINT_FALLBACK: Record<WorkspaceMentionHint, string> = {
  searching: "Searching…",
  need_agent: "Start the agent to mention workspace files",
  failed: "Could not search workspace files",
  typeToSearch: "Type a file name to search",
  typeMore: "Type at least two characters to search files",
  filesEmpty: "No matching files",
};

interface MentionPickerMenuProps {
  items: MentionPick[];
  query: string;
  agents?: MentionAgentOption[];
  subagents?: AgentSubagentSummary[];
  filesLoading?: boolean;
  filesError?: "need_agent" | "failed" | null;
  activeIndex: number;
  onSelect: (pick: MentionPick) => void;
  onHover: (index: number) => void;
}

export default function MentionPickerMenu({
  items,
  query,
  agents = [],
  subagents = [],
  filesLoading = false,
  filesError = null,
  activeIndex,
  onSelect,
  onHover,
}: MentionPickerMenuProps) {
  const { t } = useTranslation();

  const connSection = t("mention.connectors", "Connectors");
  const agentSection = t("mention.experts", "Experts");
  const subagentSection = t("mention.subagents", "Subagents");
  const fileSection = t("mention.files", "Workspace files");

  const sectionFor = (item: MentionPick) => {
    if (item.kind === "connector") return connSection;
    if (item.kind === "subagent") return subagentSection;
    if (item.kind === "file") return fileSection;
    return agentSection;
  };

  const fileCount = items.filter((item) => item.kind === "file").length;
  const hint = workspaceMentionHintState({
    query,
    loading: filesLoading,
    error: filesError,
    fileCount,
  });
  const fileHint = hint ? t(HINT_KEYS[hint], HINT_FALLBACK[hint]) : "";
  const hasFilePick = fileCount > 0;

  if (items.length === 0 && !fileHint) {
    return (
      <div className={styles.mentionMenu}>
        <div className={styles.mentionEmpty}>
          {t("mention.empty", "No matches")}
        </div>
      </div>
    );
  }

  const sections: { title: string; items: MentionPick[] }[] = [];
  for (const item of items) {
    const title = sectionFor(item);
    const last = sections[sections.length - 1];
    if (last?.title === title) last.items.push(item);
    else sections.push({ title, items: [item] });
  }
  const showFileHintHeader =
    Boolean(fileHint) &&
    !hasFilePick &&
    sections[sections.length - 1]?.title !== fileSection;

  let flatIndex = -1;
  return (
    <div className={styles.mentionMenu}>
      {sections.map((section) => (
        <div key={section.title}>
          <div className={styles.mentionCategory}>{section.title}</div>
          {section.items.map((item) => {
            flatIndex += 1;
            const idx = flatIndex;
            const active = idx === activeIndex;
            let icon;
            if (item.kind === "connector") {
              icon = <Plug size={14} />;
            } else if (item.kind === "file") {
              icon = <FileText size={14} />;
            } else if (item.kind === "subagent") {
              const sub = subagents.find((s) => s.slug === item.slug);
              icon = <span aria-hidden>{sub?.emoji || "🤖"}</span>;
            } else {
              const agent = agents.find((a) => a.agent_id === item.agent_id);
              icon = (
                <ExpertAgentAvatar
                  iconName={agent?.icon_name}
                  iconUrl={agent?.icon_url}
                  color={agent?.color}
                  size={20}
                  iconSize={11}
                />
              );
            }
            const pathHint =
              item.kind === "file" && item.path !== item.label ? item.path : "";
            return (
              <button
                key={mentionPickKey(item)}
                type="button"
                className={`${styles.mentionItem} ${
                  active ? styles.mentionItemActive : ""
                }`}
                onMouseEnter={() => onHover(idx)}
                onClick={() => onSelect(item)}
              >
                <span className={styles.mentionIcon}>{icon}</span>
                <span className={styles.mentionLabelWrap}>
                  <span className={styles.mentionLabel}>{item.label}</span>
                  {pathHint ? (
                    <span className={styles.mentionPath}>{pathHint}</span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </div>
      ))}
      {fileHint ? (
        <div>
          {showFileHintHeader && (
            <div className={styles.mentionCategory}>{fileSection}</div>
          )}
          <div className={styles.mentionHint}>{fileHint}</div>
        </div>
      ) : null}
    </div>
  );
}
