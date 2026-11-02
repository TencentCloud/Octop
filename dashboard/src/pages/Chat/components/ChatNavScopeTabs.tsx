import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { CHAT_NAV_SCOPES, type ChatNavScope } from "../utils/chatNavScope";
import styles from "../index.module.less";

const NAV_SCOPE_LABELS: Record<
  ChatNavScope,
  { key: string; fallback: string; emptyKey: string; emptyFallback: string }
> = {
  experts: {
    key: "chat.navScopeExperts",
    fallback: "专家",
    emptyKey: "chat.navScopeEmptyExperts",
    emptyFallback: "还没有专家",
  },
  teams: {
    key: "chat.navScopeTeams",
    fallback: "团队",
    emptyKey: "chat.navScopeEmptyTeams",
    emptyFallback: "还没有团队",
  },
  cloud: {
    key: "chat.navScopeCloud",
    fallback: "云端",
    emptyKey: "chat.navScopeEmptyCloud",
    emptyFallback: "还没有云端协同",
  },
};

export function chatNavScopeEmptyCopy(scope: ChatNavScope): {
  key: string;
  fallback: string;
} {
  const meta = NAV_SCOPE_LABELS[scope];
  return { key: meta.emptyKey, fallback: meta.emptyFallback };
}

const NAV_SCOPE_CREATE: Partial<
  Record<ChatNavScope, { key: string; fallback: string; to: string }>
> = {
  teams: {
    key: "chat.navScopeCreateTeam",
    fallback: "创建第一个团队",
    to: "/experts?tab=teams",
  },
  cloud: {
    key: "chat.navScopeCreateCloud",
    fallback: "添加云端协同",
    to: "/bridge",
  },
};

/** Empty team / cloud list, with a link to create the first one. */
export function ChatNavScopeEmpty({ scope }: { scope: ChatNavScope }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const copy = chatNavScopeEmptyCopy(scope);
  const action = NAV_SCOPE_CREATE[scope];
  return (
    <div className={styles.sessionEmptyAgents}>
      <p className={styles.sessionEmptyAgentsText}>
        {t(copy.key, copy.fallback)}
      </p>
      {action ? (
        <button
          type="button"
          className={styles.sessionEmptyAgentsLink}
          onClick={() => navigate(action.to)}
        >
          {t(action.key, action.fallback)}
        </button>
      ) : null}
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
            className={`${styles.sessionScopeTab} ${
              selected ? styles.sessionScopeTabActive : ""
            }`}
            onClick={() => onChange(scope)}
          >
            {t(meta.key, meta.fallback)}
          </button>
        );
      })}
    </div>
  );
}
