import { useTranslation } from "react-i18next";
import cx from "classnames";
import { Plus } from "lucide-react";
import { CHAT_NAV_SCOPES, type ChatNavScope } from "../utils/chatNavScope";
import styles from "../index.module.less";

const NAV_SCOPE_LABELS: Record<
  ChatNavScope,
  {
    key: string;
    fallback: string;
    emptyKey: string;
    emptyFallback: string;
    hintKey: string;
    hintFallback: string;
  }
> = {
  experts: {
    key: "chat.navScopeExperts",
    fallback: "专家",
    emptyKey: "chat.navScopeEmptyExperts",
    emptyFallback: "还没有专家",
    hintKey: "chat.noAgentsHint",
    hintFallback: "从专家列表选择模板，快速创建你的第一个 AI 专家。",
  },
  teams: {
    key: "chat.navScopeTeams",
    fallback: "团队",
    emptyKey: "chat.navScopeEmptyTeams",
    emptyFallback: "还没有团队",
    hintKey: "chat.navScopeEmptyTeamsHint",
    hintFallback: "把几个专家组成团队，一起处理同一件事。",
  },
  cloud: {
    key: "chat.navScopeCloud",
    fallback: "云端",
    emptyKey: "chat.navScopeEmptyCloud",
    emptyFallback: "还没有云端协同",
    hintKey: "chat.navScopeEmptyCloudHint",
    hintFallback: "连上一台云端 Octop，这里会列出那边的专家和团队。",
  },
};

const NAV_SCOPE_CREATE: Record<
  ChatNavScope,
  { key: string; fallback: string }
> = {
  experts: { key: "chat.createExpert", fallback: "去创建专家" },
  teams: {
    key: "chat.navScopeCreateTeam",
    fallback: "创建第一个团队",
  },
  cloud: {
    key: "chat.navScopeCreateCloud",
    fallback: "添加云端协同",
  },
};

const NAV_CREATE_BUTTON: Record<
  ChatNavScope,
  { key: string; fallback: string }
> = {
  experts: { key: "chat.navCreateExpert", fallback: "创建专家" },
  teams: { key: "chat.navCreateTeam", fallback: "创建团队" },
  cloud: { key: "chat.navCreateCloud", fallback: "添加云端" },
};

/** Create action under the scope tabs. Opens a right-hand drawer. */
export function ChatNavCreateButton({
  scope,
  onCreate,
}: {
  scope: ChatNavScope;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  const action = NAV_CREATE_BUTTON[scope];
  return (
    <button
      type="button"
      className={styles.sessionScopeCreate}
      onClick={onCreate}
    >
      <Plus size={14} strokeWidth={2} aria-hidden />
      {t(action.key, action.fallback)}
    </button>
  );
}

/** Empty expert / team / cloud list. The action opens a drawer. */
export function ChatNavScopeEmpty({
  scope,
  onCreate,
}: {
  scope: ChatNavScope;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  const meta = NAV_SCOPE_LABELS[scope];
  const action = NAV_SCOPE_CREATE[scope];
  return (
    <div className={styles.sessionEmptyAgents}>
      <p className={styles.sessionEmptyAgentsTitle}>
        {t(meta.emptyKey, meta.emptyFallback)}
      </p>
      <p className={styles.sessionEmptyAgentsText}>
        {scope === "experts"
          ? t(meta.hintKey)
          : t(meta.hintKey, meta.hintFallback)}
      </p>
      <button
        type="button"
        className={styles.sessionEmptyAgentsLink}
        onClick={onCreate}
      >
        {scope === "experts" ? t(action.key) : t(action.key, action.fallback)}
      </button>
    </div>
  );
}

/** Expert / team / cloud switch under the chat nav search box. */
export default function ChatNavScopeTabs({
  value,
  onChange,
}: {
  value: ChatNavScope;
  onChange: (scope: ChatNavScope) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={styles.sessionScopeTabs} role="tablist">
      {CHAT_NAV_SCOPES.map((scope) => {
        const meta = NAV_SCOPE_LABELS[scope];
        const selected = value === scope;
        return (
          <button
            key={scope}
            type="button"
            role="tab"
            aria-selected={selected}
            className={cx(
              styles.sessionScopeTab,
              selected && styles.sessionScopeTabActive,
            )}
            onClick={() => onChange(scope)}
          >
            {t(meta.key, meta.fallback)}
          </button>
        );
      })}
    </div>
  );
}
