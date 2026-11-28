/**
 * ChatGitPanel — standalone git review panel for the chat dock: change list
 * on the left, unified diff on the right, quick actions and history on top.
 */

import { useCallback, useEffect, useState } from "react";
import { App, Button, Empty, Spin, Tooltip } from "antd";
import {
  ChevronDown,
  ChevronRight,
  FileDiff,
  GitBranch,
  GitCommitHorizontal,
  History,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  gitApi,
  type GitCommitEntry,
  type GitDiff,
} from "../../../api/modules/git";
import { apiErrorMessage } from "../../../utils/apiError";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import {
  useWorkspaceGit,
  type UseWorkspaceGitResult,
} from "../../Agent/Workspace/components/gitStatus";
import GitChangeList from "./GitChangeList";
import GitCommitDialog from "./GitCommitDialog";
import GitDiffView from "../../Agent/Workspace/components/GitDiffView";
import styles from "../../Agent/Workspace/index.module.less";

interface GitDiffPaneProps {
  agentId: string;
  path: string;
  staged: boolean;
}

function GitDiffPane({ agentId, path, staged }: GitDiffPaneProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<GitDiff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    gitApi
      .diff(agentId, path, staged)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(apiErrorMessage(err, t("workspace.readFailed", "读取失败")));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, path, staged, t]);

  return (
    <>
      <div className={styles.gitDiffHeader}>
        <span className={styles.gitDiffHeaderPath} title={path}>
          {path}
          {staged ? ` · ${t("git.stagedLabel", "已暂存")}` : ""}
        </span>
      </div>
      {loading ? (
        <div className={styles.viewerLoading}>
          <Spin />
        </div>
      ) : error ? (
        <div className={styles.gitNotice} data-testid="git-diff-error">
          {error}
        </div>
      ) : (
        <GitDiffView diff={data?.diff ?? ""} truncated={data?.truncated} />
      )}
    </>
  );
}

interface ChatGitPanelProps {
  agentId: string;
  streaming?: boolean;
  /** External focus request (e.g. message-stream Review): select this file. */
  focusPath?: string | null;
  /** Bumped on each focus request so a repeated path re-triggers selection. */
  focusSeq?: number;
  onOpenFile?: (path: string) => void;
  /** Open the full commit graph in a separate dock tab. */
  onOpenHistory?: () => void;
}

export default function ChatGitPanel({
  agentId,
  streaming = false,
  focusPath = null,
  focusSeq = 0,
  onOpenFile,
  onOpenHistory,
}: ChatGitPanelProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const timeZone = useServerTimezone();
  const git: UseWorkspaceGitResult = useWorkspaceGit(agentId, {
    enabled: true,
    streaming,
  });
  const [selected, setSelected] = useState<{
    path: string;
    staged: boolean;
  } | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [log, setLog] = useState<GitCommitEntry[] | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [commitOpen, setCommitOpen] = useState(false);

  const { status, loading, error } = git;
  const isRepo = status?.is_repo ?? false;
  const gitOk = status?.git_available ?? true;

  // Drop the selection when the file no longer appears in the status list.
  useEffect(() => {
    if (!selected || !status) return;
    const stillThere = status.files.some(
      (f) => f.path === selected.path && f.staged === selected.staged,
    );
    if (!stillThere) setSelected(null);
  }, [status, selected]);

  // External focus requests (message-stream Review rows) select the file's
  // unstaged row first, falling back to the staged row.
  useEffect(() => {
    if (!focusPath || !status) return;
    const target = focusPath.replace(/^[\\/]+/, "");
    const unstaged = status.files.find((f) => f.path === target && !f.staged);
    const any = status.files.find((f) => f.path === target);
    const hit = unstaged ?? any;
    if (hit) {
      setSelected({ path: hit.path, staged: hit.staged });
    }
  }, [focusPath, focusSeq, status]);

  const loadLog = useCallback(async () => {
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
      const ok = await git.act(op);
      if (ok && okText) message.success(okText);
      if (!ok) message.error(t("git.opFailed", "Git 操作失败"));
    },
    [git, message, t],
  );

  if (!isRepo) {
    return (
      <div className={styles.gitPanelEmpty} data-testid="git-panel-empty">
        <Empty
          description={
            error ??
            (!gitOk
              ? t("git.gitUnavailable", "服务器未安装 git")
              : t("git.notARepo", "当前工作区不是 Git 仓库"))
          }
        />
      </div>
    );
  }

  return (
    <div className={styles.gitPanel} data-testid="git-panel">
      <div className={styles.gitToolsCard} data-testid="git-tools-card">
        <div className={styles.gitToolsHeader}>
          <span
            className={styles.gitToolsBranch}
            title={status?.upstream ?? undefined}
            data-testid="git-tools-branch"
          >
            <GitBranch size={14} aria-hidden />
            <span className={styles.gitToolsBranchName}>
              {status?.branch ?? "—"}
            </span>
          </span>
          {status?.upstream && (
            <span className={styles.gitToolsMeta} data-testid="git-tools-ahead">
              ⇅{status.ahead}/{status.behind}
            </span>
          )}
          <span className={styles.gitToolsStat} data-testid="git-tools-changes">
            <FileDiff size={13} aria-hidden />
            <span>{t("git.tools.changes", "Changes")}</span>
            <span className={styles.gitCommitTotals}>
              <span className={styles.gitRowAdded}>+{status?.added ?? 0}</span>{" "}
              <span className={styles.gitRowRemoved}>
                −{status?.removed ?? 0}
              </span>
            </span>
          </span>
          <span className={styles.gitToolsSpacer} />
          <Tooltip title={t("git.tools.commitOrPush", "Commit or push")}>
            <Button
              type="text"
              size="small"
              disabled={streaming}
              onClick={() => setCommitOpen(true)}
              aria-label={t("git.tools.commitOrPush", "Commit or push")}
              title={
                streaming ? t("git.writeDisabledWhileStreaming") : undefined
              }
              data-testid="git-commit-open"
              icon={<GitCommitHorizontal size={14} />}
            />
          </Tooltip>
          <Tooltip title={t("git.tools.history", "History")}>
            <Button
              type="text"
              size="small"
              onClick={() => onOpenHistory?.()}
              aria-label={t("git.tools.history", "History")}
              data-testid="git-history-open"
              icon={<History size={14} />}
            />
          </Tooltip>
          <Tooltip title={t("common.refresh")}>
            <Button
              size="small"
              icon={
                <RefreshCw
                  size={13}
                  className={loading ? styles.gitSpin : undefined}
                />
              }
              onClick={() => void git.refresh()}
              aria-label={t("common.refresh")}
            />
          </Tooltip>
        </div>
      </div>

      <div className={styles.gitPanelBody}>
        <div className={styles.gitPanelList}>
          {status && (
            <GitChangeList
              status={status}
              streaming={streaming}
              selectedPath={selected?.path ?? null}
              selectedStaged={selected?.staged ?? false}
              onSelect={(path, staged) => setSelected({ path, staged })}
              onOpenFile={(path) => onOpenFile?.(path)}
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
          )}
          <button
            type="button"
            className={styles.gitLogToggle}
            onClick={() => {
              setLogOpen((v) => !v);
              if (!logOpen && log === null) void loadLog();
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

        <div className={styles.gitPanelDiff}>
          {selected ? (
            <GitDiffPane
              agentId={agentId}
              path={selected.path}
              staged={selected.staged}
            />
          ) : (
            <div className={styles.gitEmpty} data-testid="git-diff-empty">
              {t("git.pickFile", "选择文件以查看差异")}
            </div>
          )}
        </div>
      </div>

      {status && (
        <GitCommitDialog
          open={commitOpen}
          agentId={agentId}
          status={status}
          streaming={streaming}
          onClose={() => setCommitOpen(false)}
          onDone={() => {
            void git.refresh();
            if (logOpen) void loadLog();
            else setLog(null);
          }}
        />
      )}
    </div>
  );
}
