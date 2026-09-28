import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Input, Tag, Tooltip } from "antd";
import { ListTodo, Send, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  projectsApi,
  type ProjectMember,
  type ProjectTask,
} from "../../../api/modules/projects";
import { buildDashboardChatWsUrl } from "../../../api/modules/wsChat";
import { ChipButton, ChipToolbar } from "../../../components/ChipToolbar";
import { AgentPicker } from "./AgentPicker";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { useProjectMembers } from "../../../hooks/useProjectMembers";
import styles from "./QuickInput.module.less";

/**
 * Project quick input — "send a message to the project's expert" (PLAN §3).
 *
 * Send-only by contract (`G3-Q2`): the turn really runs and its reply frames do
 * stream back on the same socket, but this component **renders nothing of the
 * reply**. It reads exactly two terminal frames and ignores everything else:
 *
 * * whitelist = `done` / `error`; **anything else is ignored explicitly**
 *   ("not in the whitelist ⇒ ignore", never "known list ⇒ ignore"), so a frame
 *   type added later cannot end the turn by accident;
 * * `error` **locks** the failure path — the backend emits `error` *followed by*
 *   `done` in six places (an invalid frame, an empty message, a failed turn
 *   preparation, a missing thread, a non-streaming processor, an exception), so
 *   treating `done` as the only terminal would report those failures as success;
 * * `done` only wins when **no `error` was seen**; the first terminal state wins
 *   and the socket closes right after it;
 * * 10s without a terminal → close and treat it as sent (no `token` does not
 *   mean "not delivered");
 * * failure keeps the text — only success clears it (`G3-Q3`).
 *
 * The target expert is chosen deterministically from
 * `project_members(subject_type='agent')` (PLAN §3.2); no project ↔ conversation
 * association is written anywhere (`project_rooms` stays dead, the dispatch
 * thread is untouched).
 */

const TERMINAL_FRAMES = new Set(["done", "error"]);

/** PLAN §3.4-4: no terminal frame within this window → close and mark sent. */
const TERMINAL_TIMEOUT_MS = 10_000;

export interface QuickInputProps {
  projectId: string;
  /**
   * The parent already knows the project's status; passing it keeps the UX gate
   * below correct for archived (read-only) projects without a second read of the
   * same project row. Optional: an absent value means "not archived".
   */
  archived?: boolean;
}

/** Roles that satisfy the frozen `PROJECT_WRITE` action (PLAN §3.5 matrix). */
const WRITE_ROLES = new Set(["owner", "admin", "member"]);

/** The caller's own membership row, i.e. the role they hold in this project. */
function myProjectRole(
  members: ProjectMember[],
  userId: number | undefined,
): string | null {
  if (userId === undefined) return null;
  const mine = members.find(
    (member) => member.subject_type === "user" && member.user_id === userId,
  );
  return mine?.role ?? null;
}

/**
 * Default recipient = the deterministic first agent (PLAN §2.3): sort by
 * ``(created_at ASC, subject_id ASC)`` and take the head. The sort is done
 * here on purpose — it must never depend on the order the API/DB returned, and
 * ``subject_id`` breaks ties so the result is a total order.
 */
export function defaultRecipient(
  members: ProjectMember[],
): ProjectMember | null {
  const agents = members
    .filter((member) => member.subject_type === "agent")
    .sort((a, b) => {
      if (a.created_at !== b.created_at) return a.created_at - b.created_at;
      if (a.subject_id === b.subject_id) return 0;
      return a.subject_id < b.subject_id ? -1 : 1;
    });
  return agents[0] ?? null;
}

/** Candidate set for the picker: agent members only (PLAN §2.1 / AC-D2-1). */
export function agentMembers(members: ProjectMember[]): ProjectMember[] {
  return members.filter((member) => member.subject_type === "agent");
}

/**
 * Reference titles are plain text on a single line: a newline would forge a
 * second quote line, and a leading `>` would collide with the quote marker
 * (PLAN §3.3 / FIND-9). The server does not parse these lines at all.
 */
function referenceTitle(title: string): string {
  const folded = title.replace(/[\r\n]+/g, " ").trim();
  return folded.startsWith(">") ? ` ${folded}` : folded;
}

/** The frozen message body: the text, a blank line, then one line per reference. */
export function composeMessage(
  text: string,
  references: ProjectTask[],
): string {
  if (references.length === 0) return text;
  const lines = references.map(
    (task) =>
      `> 引用任务：${referenceTitle(task.title)}（task_id=${task.task_id}）`,
  );
  return [text, "", ...lines].join("\n");
}

export default function QuickInput({
  projectId,
  archived = false,
}: QuickInputProps) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [referenceIds, setReferenceIds] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [failed, setFailed] = useState(false);
  const [referencesDropped, setReferencesDropped] = useState(false);

  const currentUser = useCurrentUser();
  const { members, loading: membersLoading } = useProjectMembers(projectId);
  const { data: tasks, loading: tasksLoading } = useAsyncResource<
    ProjectTask[]
  >([], () => projectsApi.listTasks(projectId), [projectId], {
    t,
    errorFallback: t("projects.loadFailed"),
    logLabel: "project-quick-input",
  });

  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<number | null>(null);
  /** Only an `error` frame sets this — it is what refuses a later `done`. */
  const failedRef = useRef(false);
  /** First terminal state wins. */
  const settledRef = useRef(false);

  const agents = useMemo(() => agentMembers(members), [members]);
  const initialRecipient = useMemo(() => defaultRecipient(members), [members]);
  /** Selected recipient: in-memory only — nothing is persisted anywhere. */
  const [recipient, setRecipient] = useState<ProjectMember | null>(null);
  /**
   * PLAN §2.2 state machine: the selection survives a members re-read while the
   * agent is still listed; if it disappeared we fall back to the deterministic
   * default (which may be null → R10 disabled + copy). ``recipient === null``
   * before the first read is also covered: it is seeded from the default.
   */
  useEffect(() => {
    setRecipient((current) => {
      if (current && agents.some((a) => a.subject_id === current.subject_id)) {
        return current;
      }
      return initialRecipient;
    });
  }, [agents, initialRecipient]);

  const agent = recipient;

  /**
   * ★ UX 门（非安全控制）— ★ UX gate, **not a security boundary**.
   *
   * 该门**不是安全边界**：绕过 UI 直接开 WS 仍受 `assert_agent_access` 管；本门只避免
   * 「点了必然失败」的坏体验。The real boundary is the WebSocket's own
   * `assert_agent_access` (`chat/ws.py` → `api/common/agent.py`); `PLAN §3.5`'s
   * project-side check has no server-side landing point this round, and the
   * frontend must not grow a second permission judgement — so this reads the
   * role the members feed already carries (`GET /projects/{pid}/members`) plus
   * the current user, and nothing else. No extra read, no permission probe.
   */
  const myRole = useMemo(
    () => myProjectRole(members, currentUser?.id),
    [members, currentUser],
  );
  // Until the role is known the input is simply absent: showing "no permission"
  // and then the input would be worse than one quiet render.
  const roleKnown = !membersLoading;
  const writeAllowed = !archived && myRole !== null && WRITE_ROLES.has(myRole);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const closeSocket = useCallback(() => {
    const socket = socketRef.current;
    socketRef.current = null;
    if (!socket) return;
    // Drop the handlers first: the close we cause is not a failure signal.
    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    socket.onerror = null;
    try {
      socket.close();
    } catch {
      // already closed
    }
  }, []);

  useEffect(
    () => () => {
      clearTimer();
      closeSocket();
    },
    [clearTimer, closeSocket],
  );

  /** The single terminal writer: whichever frame/timeout gets here first wins. */
  const settle = useCallback(
    (next: "sent" | "failed") => {
      if (settledRef.current) return;
      settledRef.current = true;
      clearTimer();
      closeSocket();
      setSending(false);
      setSent(next === "sent");
      setFailed(next === "failed");
      if (next === "sent") {
        // Only a delivery clears the compose state (G3-Q3).
        setText("");
        setReferenceIds([]);
      }
    },
    [clearTimer, closeSocket],
  );

  const submit = async () => {
    const body = text.trim();
    if (!body || !recipient || sending) return;

    // References are resolved against the list **at submit time**: a task
    // deleted meanwhile is dropped, the rest still goes out (PLAN §3.3). Only
    // read again when there is something to resolve; if that read fails the
    // cached list is used (stale references are still better than losing the
    // user's selection on a transient error).
    let referenceSource = tasks;
    if (referenceIds.length > 0) {
      try {
        referenceSource = await projectsApi.listTasks(projectId);
      } catch {
        referenceSource = tasks;
      }
    }
    const known = new Map(referenceSource.map((task) => [task.task_id, task]));
    const selected = referenceIds
      .map((id) => known.get(id))
      .filter((task): task is ProjectTask => task !== undefined);
    const dropped = selected.length !== referenceIds.length;
    if (dropped) {
      setReferenceIds(selected.map((task) => task.task_id));
      setReferencesDropped(true);
    }

    // 换人 ⇒ 新建会话（沿用 G3-Q1）：仍不传 thread_id，目标 = 所选收件人。
    const socket = new WebSocket(buildDashboardChatWsUrl(recipient.subject_id));
    socketRef.current = socket;
    failedRef.current = false;
    settledRef.current = false;
    setSent(false);
    setFailed(false);
    setSending(true);

    socket.onopen = () => {
      // No ``thread_id``: the server derives the session key and creates the
      // conversation on first use (PLAN §3.1).
      socket.send(
        JSON.stringify({
          type: "user_turn",
          text: composeMessage(body, selected),
          // ★ 项目页发送必须带项目上下文（批次十）—— 全局对话页那条路径不带（镜像风险）。
          project_id: projectId,
        }),
      );
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      let frame: { type?: unknown } | null = null;
      try {
        frame = JSON.parse(String(event.data)) as { type?: unknown };
      } catch {
        return; // not a JSON frame → not a terminal
      }
      const type = typeof frame?.type === "string" ? frame.type : "";
      // ★ Whitelist only. Every other frame — token / reasoning / usage /
      // tool_* / hitl_required / attachment / state_* / custom / turn_status /
      // pong / anything added later — is ignored explicitly.
      if (!TERMINAL_FRAMES.has(type)) return;
      if (type === "error") {
        // ★ Lock the failure path: a later ``done`` must not flip this.
        failedRef.current = true;
        settle("failed");
        return;
      }
      settle(failedRef.current ? "failed" : "sent");
    };

    socket.onerror = () => {
      // The close that follows carries the failure.
    };

    socket.onclose = () => {
      // Any close before a terminal frame is a failure — 4001 (bad token),
      // 4003 (agent not accessible), 4404, 1011, or a close before the send.
      settle("failed");
    };

    timerRef.current = window.setTimeout(() => {
      // Delivered but quiet: no terminal frame, no error.
      settle("sent");
    }, TERMINAL_TIMEOUT_MS);
  };

  const references = referenceIds
    .map((id) => tasks.find((task) => task.task_id === id))
    .filter((task): task is ProjectTask => task !== undefined);

  const canSend = Boolean(agent) && text.trim().length > 0 && !sending;

  return (
    <section className={styles.wrapper} data-testid="project-quick-input">
      {!roleKnown ? null : writeAllowed ? (
        <div className={styles.row}>
          <Input.TextArea
            className={styles.input}
            value={text}
            disabled={!agent}
            placeholder={t("projects.quickInputPlaceholder")}
            aria-label={t("projects.quickInputPlaceholder")}
            /* PLAN §1：自适应高度（1 行起、6 行封顶、超出内部滚动）；软换行由
               textarea 默认 `wrap=soft` 提供 —— 不手写高度计算（§0 事实 4）。 */
            autoSize={{ minRows: 1, maxRows: 6 }}
            onChange={(event) => setText(event.target.value)}
            /* PLAN §1：antd TextArea 没有 pressEnter 事件 → 用 onKeyDown：
               Enter 发送、Shift+Enter 换行（默认行为）。 */
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
          />
          <Button
            type="primary"
            icon={<Send size={14} />}
            loading={sending}
            disabled={!canSend}
            onClick={() => void submit()}
          >
            {sending
              ? t("projects.quickInputSending")
              : t("projects.quickInputSend")}
          </Button>
        </div>
      ) : null}

      <div className={styles.meta}>
        {/* Always visible, never a tooltip-only hint (PLAN §3.2 / AC-G3-6). */}
        {!roleKnown ? null : !writeAllowed ? (
          <span className={styles.noAgent} data-testid="quick-input-readonly">
            {t("common.noPermission")}
          </span>
        ) : agent ? (
          <AgentPicker
            agents={agents}
            value={agent}
            onChange={setRecipient}
            disabled={sending}
          />
        ) : (
          <span className={styles.noAgent} data-testid="quick-input-no-agent">
            {t("projects.quickInputNoAgent")}
          </span>
        )}
        {sent ? (
          <span className={styles.sent} data-testid="quick-input-sent">
            {t("projects.quickInputSent")}
          </span>
        ) : null}
        {failed ? (
          <span
            className={styles.failed}
            role="alert"
            data-testid="quick-input-failed"
          >
            {t("projects.quickInputFailed")}
          </span>
        ) : null}
        {referencesDropped ? (
          <span
            className={styles.failed}
            role="status"
            data-testid="quick-input-ref-removed"
          >
            {t("projects.quickInputRefRemoved")}
          </span>
        ) : null}
      </div>

      {!writeAllowed ? null : (
        <ChipToolbar testId="quick-input-references">
          <ChipButton
            icon={<ListTodo size={14} />}
            label={t("projects.quickInputRefTask")}
            value={references.length > 0 ? String(references.length) : null}
            active={references.length > 0}
            disabled={tasksLoading}
            ariaLabel={t("projects.quickInputRefTask")}
          >
            <div className={styles.menu}>
              {tasks.length === 0 ? (
                <div className={styles.menuEmpty}>{t("projects.noTasks")}</div>
              ) : (
                tasks.map((task) => {
                  const active = referenceIds.includes(task.task_id);
                  return (
                    <button
                      key={task.task_id}
                      type="button"
                      aria-pressed={active}
                      className={`${styles.menuOption} ${
                        active ? styles.menuOptionActive : ""
                      }`}
                      onClick={() =>
                        setReferenceIds((current) =>
                          active
                            ? current.filter((id) => id !== task.task_id)
                            : [...current, task.task_id],
                        )
                      }
                    >
                      <span>{task.title}</span>
                    </button>
                  );
                })
              )}
            </div>
          </ChipButton>

          {references.map((task) => (
            <span key={task.task_id} className={styles.reference}>
              <Tag className={styles.referenceTag}>{task.title}</Tag>
              <Tooltip title={t("common.delete")}>
                <button
                  type="button"
                  className={styles.referenceRemove}
                  aria-label={`${t("projects.quickInputRefTask")} ${
                    task.title
                  }`}
                  onClick={() =>
                    setReferenceIds((current) =>
                      current.filter((id) => id !== task.task_id),
                    )
                  }
                >
                  <X size={12} />
                </button>
              </Tooltip>
            </span>
          ))}
        </ChipToolbar>
      )}
    </section>
  );
}
