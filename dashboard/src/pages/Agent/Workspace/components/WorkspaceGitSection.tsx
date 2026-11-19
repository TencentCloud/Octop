/**
 * WorkspaceGitSection — collapsible git summary embedded at the top of the
 * workspace drawer (方案 B). Owns status fetching and the change list;
 * diff review is delegated through onReview.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { App, Button, Input, Popconfirm, Spin, Tooltip } from "antd";
import {
  ChevronDown,
  ChevronRight,
  GitBranch,
  Plus,
  RefreshCw,
  RotateCcw,
  Undo2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  gitApi,
  type GitFileChange,
  type GitStatus,
} from "../../../../api/modules/git";
import { apiErrorMessage } from "../../../../utils/apiError";
import { useServerTimezone } from "../../../../hooks/useServerTimezone";
import { formatServerIsoDateTime } from "../../../../utils/formatMessageTime";
import { isImeComposing } from "../../../../utils/ime";
import type { GitCommitEntry } from "../../../../api/modules/git";
import styles from "../index.module.less";

const STATUS_LETTER: Record<string, string> = {
  modified: "M",
  added: "A",
  deleted: "D",
  renamed: "R",
  copied: "C",
  typechange: "T",
  untracked: "U",
  conflicted: "!",
};

const STATUS_KEY: Record<string, string> = {
  modified: "git.statusModified",
  added: "git.statusAdded",
  deleted: "git.statusDeleted",
  renamed: "git.statusRenamed",
  copied: "git.statusCopied",
  typechange: "git.statusTypechange",
  untracked: "git.statusUntracked",
  conflicted: "git.statusConflicted",
};

export interface GitTreeBadges {
  /** workspace path (leading ``/``) → status letter */
  fileStatus: Map<string, string>;
  /** workspace dir path (leading ``/``) with changes inside */
  changedDirs: Set<string>;
}

export function gitTreeBadges(status: GitStatus | null): GitTreeBadges | null {
  if (!status?.is_repo) return null;
  const fileStatus = new Map<string, string>();
  const changedDirs = new Set<string>();
  for (const change of status.files) {
    const rel = change.path.replace(/\/+$/, "");
    if (!rel) continue;
    fileStatus.set(`/${rel}`, STATUS_LETTER[change.status] ?? "M");
    let parent = rel;
    for (;;) {
      const idx = parent.lastIndexOf("/");
      if (idx < 0) break;
      parent = parent.slice(0, idx);
      if (parent) changedDirs.add(`/${parent}`);
    }
  }
  return { fileStatus, changedDirs };
}

export interface UseWorkspaceGitResult {
  status: GitStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  act: (op: (agentId: string) => Promise<unknown>) => Promise<boolean>;
}

export function useWorkspaceGit(
  agentId: string | null | undefined,
  opts: { enabled: boolean; streaming?: boolean; onMutated?: () => void },
): UseWorkspaceGitResult {
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onMutatedRef = useRef(opts.onMutated);
  onMutatedRef.current = opts.onMutated;

  const refresh = useCallback(async () => {
    if (!agentId || !opts.enabled) return;
    setLoading(true);
    try {
      setStatus(await gitApi.status(agentId));
      setError(null);
    } catch (err: unknown) {
      setError(
        apiErrorMessage(
          err,
          err instanceof Error ? err.message : "git status failed",
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [agentId, opts.enabled]);

  useEffect(() => {
    if (!opts.enabled) {
      setStatus(null);
      setError(null);
      return;
    }
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, opts.enabled]);

  const prevStreaming = useRef(opts.streaming);
  useEffect(() => {
    const was = prevStreaming.current;
    prevStreaming.current = opts.streaming;
    if (was && !opts.streaming && opts.enabled) {
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.streaming]);

  const act = useCallback(
    async (op: (agentId: string) => Promise<unknown>) => {
      if (!agentId) return false;
      try {
        await op(agentId);
        await refresh();
        onMutatedRef.current?.();
        return true;
      } catch {
        return false;
      }
    },
    [agentId, refresh],
  );

  return { status, loading, error, refresh, act };
}

function fileBasename(path: string): string {
  return path.split("/").filter(Boolean).pop() || path;
}

function fileParent(path: string): string {
  const parts = path.replace(/\/+$/, "").split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

interface ChangeRowProps {
  change: GitFileChange;
  streaming: boolean;
  onReview: (path: string, staged: boolean) => void;
  onOpenFile: (path: string) => void;
  onStage: (path: string) => void;
  onUnstage: (path: string) => void;
  onDiscard: (path: string) => void;
}

function ChangeRow({
  change,
  streaming,
  onReview,
  onOpenFile,
  onStage,
  onUnstage,
  onDiscard,
}: ChangeRowProps) {
  const { t } = useTranslation();
  const letter = STATUS_LETTER[change.status] ?? "M";
  const modifier = letter === "!" ? "X" : letter;
  const parent = fileParent(change.path);
  return (
    <div
      className={styles.gitRow}
      data-testid="git-change-row"
      onClick={() => onReview(change.path, change.staged)}
    >
      <span
        className={`${styles.gitRowStatus} ${
          styles[`gitRowStatus${modifier}`] ?? ""
        }`}
        title={t(STATUS_KEY[change.status] ?? "git.statusModified")}
      >
        {letter}
      </span>
      <span className={styles.gitRowName} title={change.path}>
        {fileBasename(change.path)}
        {change.orig_path ? (
          <span className={styles.gitRowDir}>
            {" "}
            ← {fileBasename(change.orig_path)}
          </span>
        ) : null}
      </span>
      <span className={styles.gitRowDir}>{parent}</span>
      {change.added != null && (
        <span className={styles.gitRowAdded}>+{change.added}</span>
      )}
      {change.removed != null && (
        <span className={styles.gitRowRemoved}>−{change.removed}</span>
      )}
      <span className={styles.gitRowActions}>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onReview(change.path, change.staged);
          }}
        >
          {t("git.review", "Review")}
        </button>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onOpenFile(change.path);
          }}
        >
          {t("git.open", "打开")}
        </button>
        {change.staged ? (
          <Tooltip title={t("git.unstage", "取消暂存")}>
            <button
              type="button"
              disabled={streaming}
              aria-label={t("git.unstage", "取消暂存")}
              onClick={(e) => {
                e.stopPropagation();
                onUnstage(change.path);
              }}
            >
              <RotateCcw size={12} strokeWidth={2} />
            </button>
          </Tooltip>
        ) : (
          <Tooltip title={t("git.stage", "暂存")}>
            <button
              type="button"
              disabled={streaming}
              aria-label={t("git.stage", "暂存")}
              onClick={(e) => {
                e.stopPropagation();
                onStage(change.path);
              }}
            >
              <Plus size={12} strokeWidth={2} />
            </button>
          </Tooltip>
        )}
        {!change.staged && (
          <Popconfirm
            title={t("git.discardConfirmTitle", "放弃更改？")}
            description={t("git.discardConfirmBody", {
              defaultValue:
                "将丢失该文件的未提交更改（未跟踪文件会被删除），不可恢复。",
            })}
            okText={t("git.discard", "放弃")}
            cancelText={t("common.cancel", "取消")}
            okButtonProps={{ danger: true }}
            disabled={streaming}
            onConfirm={() => onDiscard(change.path)}
          >
            <Tooltip
              title={
                streaming
                  ? t("git.writeDisabledWhileStreaming")
                  : t("git.discard")
              }
            >
              <button
                type="button"
                disabled={streaming}
                aria-label={t("git.discard", "放弃更改")}
                onClick={(e) => e.stopPropagation()}
              >
                <Undo2 size={12} strokeWidth={2} />
              </button>
            </Tooltip>
          </Popconfirm>
        )}
      </span>
    </div>
  );
}

interface WorkspaceGitSectionProps {
  agentId: string;
  git: UseWorkspaceGitResult;
  streaming?: boolean;
  onReview: (path: string, staged: boolean) => void;
  onOpenFile: (path: string) => void;
}

export default function WorkspaceGitSection({
  agentId,
  git,
  streaming = false,
  onReview,
  onOpenFile,
}: WorkspaceGitSectionProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const timeZone = useServerTimezone();
  const [expanded, setExpanded] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [log, setLog] = useState<GitCommitEntry[] | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [commitMsg, setCommitMsg] = useState("");
  const [committing, setCommitting] = useState(false);
  const [acting, setActing] = useState(false);

  const { status, loading, error } = git;
  const isRepo = status?.is_repo ?? false;
  const gitOk = status?.git_available ?? true;
  const files = status?.files ?? [];
  const stagedFiles = files.filter((f) => f.staged);
  const unstagedFiles = files.filter(
    (f) => !f.staged && f.status !== "untracked",
  );
  const untrackedFiles = files.filter(
    (f) => !f.staged && f.status === "untracked",
  );

  const loadLog = useCallback(async () => {
    if (log || logLoading) return;
    setLogLoading(true);
    try {
      setLog(await gitApi.log(agentId, 20));
    } catch {
      setLog([]);
    } finally {
      setLogLoading(false);
    }
  }, [agentId, log, logLoading]);

  const reloadLog = useCallback(async () => {
    setLogLoading(true);
    try {
      setLog(await gitApi.log(agentId, 20));
    } catch {
      setLog([]);
    } finally {
      setLogLoading(false);
    }
  }, [agentId]);

  const runAct = useCallback(
    async (op: (agentId: string) => Promise<unknown>, okText?: string) => {
      setActing(true);
      try {
        const ok = await git.act(op);
        if (ok && okText) message.success(okText);
        if (!ok) {
          message.error(t("git.opFailed", "Git 操作失败"));
        }
      } finally {
        setActing(false);
      }
    },
    [git, message, t],
  );

  const commit = useCallback(async () => {
    const text = commitMsg.trim();
    if (!text) return;
    setCommitting(true);
    try {
      const ok = await git.act((id) => gitApi.commit(id, text));
      if (ok) {
        message.success(t("git.commitSuccess", "已提交"));
        setCommitMsg("");
        if (logOpen) {
          void reloadLog();
        } else {
          setLog(null);
        }
      } else {
        message.error(t("git.opFailed", "Git 操作失败"));
      }
    } finally {
      setCommitting(false);
    }
  }, [commitMsg, git, logOpen, message, reloadLog, t]);

  const canExpand = isRepo && gitOk;
  const filesChanged = files.length;
  const summary = isRepo
    ? t("git.filesChanged", {
        count: filesChanged,
        defaultValue: "{{count}} 个文件变更",
      }) + ` +${status?.added ?? 0} −${status?.removed ?? 0}`
    : t("git.notARepo", "当前工作区不是 Git 仓库");

  const renderGroup = (title: string, rows: GitFileChange[]) => {
    if (!rows.length) return null;
    return (
      <div key={title}>
        <div className={styles.gitGroupTitle}>{title}</div>
        {rows.map((change) => (
          <ChangeRow
            key={`${change.staged ? "s" : "w"}:${change.path}`}
            change={change}
            streaming={streaming}
            onReview={onReview}
            onOpenFile={onOpenFile}
            onStage={(path) =>
              void runAct((id) => gitApi.stage(id, [path]), t("git.staged"))
            }
            onUnstage={(path) =>
              void runAct((id) => gitApi.unstage(id, [path]))
            }
            onDiscard={(path) =>
              void runAct((id) => gitApi.discard(id, [path]))
            }
          />
        ))}
      </div>
    );
  };

  return (
    <div
      className={styles.gitSection}
      data-testid="workspace-git-section"
      data-repo={isRepo ? "true" : "false"}
    >
      <button
        type="button"
        className={styles.gitBar}
        onClick={() => canExpand && setExpanded((v) => !v)}
        aria-expanded={expanded}
        disabled={!canExpand}
        data-testid="workspace-git-bar"
      >
        <GitBranch size={14} strokeWidth={2} aria-hidden />
        <span className={styles.gitBarTitle}>{t("git.title", "Git")}</span>
        {isRepo && status?.branch && (
          <span
            className={styles.gitBranchChip}
            title={status.upstream ?? undefined}
          >
            {status.branch}
            {status.upstream ? ` ⇅${status.ahead}/${status.behind}` : ""}
          </span>
        )}
        <span
          className={cxGitSummary(isRepo)}
          data-testid="workspace-git-summary"
        >
          {summary}
        </span>
        {loading && <Spin size="small" />}
        <span className={styles.gitBarActions}>
          <RefreshCw
            size={13}
            strokeWidth={2}
            aria-hidden
            className={loading ? styles.gitSpin : undefined}
            onClick={(e) => {
              e.stopPropagation();
              void git.refresh();
            }}
          />
          {canExpand &&
            (expanded ? (
              <ChevronDown size={13} strokeWidth={2} aria-hidden />
            ) : (
              <ChevronRight size={13} strokeWidth={2} aria-hidden />
            ))}
        </span>
      </button>

      {!gitOk && isRepo && (
        <div className={styles.gitNotice}>
          {t("git.gitUnavailable", "服务器未安装 git")}
        </div>
      )}
      {error && isRepo && (
        <div className={styles.gitNotice} data-testid="workspace-git-error">
          {error}
        </div>
      )}

      {expanded && canExpand && (
        <div className={styles.gitBody}>
          {stagedFiles.length > 0 && (
            <div className={styles.gitCommitRow}>
              <Input
                size="small"
                value={commitMsg}
                onChange={(e) => setCommitMsg(e.target.value)}
                onPressEnter={(e) => {
                  if (!isImeComposing(e)) void commit();
                }}
                placeholder={t("git.commitPlaceholder", "提交信息")}
                disabled={streaming}
                data-testid="git-commit-input"
              />
              <Button
                size="small"
                type="primary"
                loading={committing}
                disabled={streaming || acting || !commitMsg.trim()}
                onClick={() => void commit()}
                title={
                  streaming ? t("git.writeDisabledWhileStreaming") : undefined
                }
              >
                {t("git.commit", "提交")} ({stagedFiles.length})
              </Button>
            </div>
          )}

          {filesChanged === 0 && (
            <div className={styles.gitEmpty}>
              {t("git.noChanges", "没有未提交的更改")}
            </div>
          )}

          {renderGroup(
            t("git.stagedGroup", {
              defaultValue: "已暂存",
              count: stagedFiles.length,
            }),
            stagedFiles,
          )}
          {renderGroup(
            t("git.changesGroup", {
              defaultValue: "更改",
              count: unstagedFiles.length,
            }),
            unstagedFiles,
          )}
          {renderGroup(
            t("git.untrackedGroup", {
              defaultValue: "未跟踪",
              count: untrackedFiles.length,
            }),
            untrackedFiles,
          )}

          <button
            type="button"
            className={styles.gitLogToggle}
            onClick={() => {
              setLogOpen((v) => !v);
              if (!logOpen) void loadLog();
            }}
            data-testid="git-log-toggle"
          >
            {logOpen ? (
              <ChevronDown size={12} strokeWidth={2} aria-hidden />
            ) : (
              <ChevronRight size={12} strokeWidth={2} aria-hidden />
            )}
            {t("git.recentCommits", "最近提交")}
          </button>
          {logOpen && (
            <div className={styles.gitLog}>
              {logLoading ? (
                <div className={styles.gitLogLoading}>
                  <Spin size="small" />
                </div>
              ) : log && log.length > 0 ? (
                log.map((entry) => (
                  <div key={entry.sha} className={styles.gitLogRow}>
                    <span className={styles.gitLogSha}>{entry.short}</span>
                    <span className={styles.gitLogMeta}>
                      {formatServerIsoDateTime(entry.date, timeZone)}
                    </span>
                    <span
                      className={styles.gitLogSubject}
                      title={entry.subject}
                    >
                      {entry.subject}
                    </span>
                  </div>
                ))
              ) : (
                <div className={styles.gitEmpty}>
                  {t("git.noCommits", "暂无提交")}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function cxGitSummary(isRepo: boolean): string {
  return isRepo ? styles.gitBarSummary : styles.gitBarSummaryMuted;
}
