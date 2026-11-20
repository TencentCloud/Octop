import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, FilePen, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { App, Button, Modal, Spin } from "antd";
import cx from "classnames";
import { useChatFilePreview } from "../ChatFilePreviewContext";
import { isWriteToolName } from "../constants";
import type { ChatMessage } from "../hooks/useChat";
import {
  fileChangeChipLabel,
  summarizeTurnFileChanges,
  type TurnFileChange,
} from "../utils/turnFileChanges";
import {
  fileCheckpointsApi,
  type RewindPreview,
  type TurnSummary,
} from "../../../api/modules/fileCheckpoints";
import { canonicalizeDockFilePath } from "../utils/dockFilePath";
import { apiErrorMessage } from "../../../utils/apiError";
import GitDiffView from "../../Agent/Workspace/components/GitDiffView";
import styles from "../index.module.less";

const FILE_CHANGE_PREVIEW = 4;
// Delay before retrying an empty summary right after a turn settles.
const SUMMARY_RETRY_MS = 800;

// The message list virtualizes turns, so scrolling remounts this card;
// cache summaries per turn (an empty summary is a cheap cached miss) so
// remounts do not re-hit the API. Cleared on rewind so the refreshed
// reverted state is authoritative again. Exported for tests to reset
// between cases; failures are never cached.
const TURN_SUMMARY_CACHE_MAX = 200;
export const turnSummaryCache = new Map<string, TurnSummary>();

function touchCacheSummary(key: string): TurnSummary {
  const value = turnSummaryCache.get(key)!;
  turnSummaryCache.delete(key);
  turnSummaryCache.set(key, value);
  return value;
}

function cacheSummary(key: string, value: TurnSummary): void {
  turnSummaryCache.delete(key);
  turnSummaryCache.set(key, value);
  while (turnSummaryCache.size > TURN_SUMMARY_CACHE_MAX) {
    const oldest = turnSummaryCache.keys().next().value;
    if (oldest === undefined) break;
    turnSummaryCache.delete(oldest);
  }
}

// Thread-first so a rewind evicts every speaker's entries in a team room
// with one prefix.
const summaryCacheKey = (
  agentId: string,
  threadId: string,
  messageId: string,
) => `${threadId}:${agentId}:${messageId}`;

function changeDir(displayPath: string): string {
  const parts = displayPath.replace(/\\/g, "/").split("/").filter(Boolean);
  parts.pop();
  return parts.length ? parts.join("/") + "/" : "";
}

/**
 * Files this reply wrote or edited: a collapsed summary bar
 * (``N files changed +A −D``) with an Undo action, expanding into per-file
 * rows. Review shows this turn's before→after diff; Open opens the file.
 * Once the turn ends the authoritative stats and undo state come from the
 * server-side checkpoints; while streaming the card estimates from the tool
 * arguments it has seen so far.
 */
export default function TurnFileChangeCard({
  messages,
  agentId,
  streaming = false,
  onOpenList,
}: {
  messages: ChatMessage[];
  agentId?: string | null;
  streaming?: boolean;
  onOpenList?: () => void;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const filePreview = useChatFilePreview();
  const threadId = filePreview?.threadId ?? null;
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const [diffPath, setDiffPath] = useState<string | null>(null);
  const [diffText, setDiffText] = useState("");
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffUnavailable, setDiffUnavailable] = useState(false);

  const [serverSummary, setServerSummary] = useState<TurnSummary | null>(null);
  const [rewindOpen, setRewindOpen] = useState(false);
  const [preview, setPreview] = useState<RewindPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const summary = useMemo(
    () => summarizeTurnFileChanges(messages, agentId),
    [messages, agentId],
  );
  const fallbackCount = useMemo(() => {
    // Write tools and edited-file stamps only: media/attachment paths would
    // turn read-only turns (e.g. a browser screenshot) into false positives.
    const edited = new Set<string>();
    for (const m of messages) {
      for (const path of m.editedFiles ?? []) {
        if (path.trim()) edited.add(path.trim());
      }
    }
    // The two signals count different units (paths vs calls); take the
    // stronger one instead of summing.
    const writeCalls = messages.filter((m) =>
      isWriteToolName(m.toolData?.name),
    ).length;
    return Math.max(edited.size, writeCalls);
  }, [messages]);

  const messageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return null;
  }, [messages]);

  const canCheckpoint = Boolean(agentId && threadId && messageId);
  const diffRequestRef = useRef(0);

  const summaryRequestRef = useRef(0);
  const summaryRetriedRef = useRef(false);
  const summaryRetryTimerRef = useRef<number | null>(null);
  const refreshSummary = useCallback(
    async (cacheEmpty = false) => {
      if (!canCheckpoint || streaming) {
        // Invalidate any in-flight summary so a late response cannot
        // repopulate serverSummary after the card fell back to the estimate.
        summaryRequestRef.current += 1;
        setServerSummary(null);
        return;
      }
      const requestId = ++summaryRequestRef.current;
      const key = summaryCacheKey(agentId!, threadId!, messageId!);
      if (turnSummaryCache.has(key)) {
        setServerSummary(touchCacheSummary(key));
        return;
      }
      try {
        const res = await fileCheckpointsApi.turnSummary(
          agentId!,
          threadId!,
          messageId!,
        );
        if (requestId !== summaryRequestRef.current) return;
        // Only the current request may touch the cache: a late response would
        // otherwise shadow a post-rewind refresh with the stale summary. An
        // empty first fetch is not cached — checkpoints are persisted after
        // the stream's done chunk, so it can legitimately race an empty
        // store — but the post-settle retry's (still-empty) result is: the
        // race window has passed, and negative-caching keeps quiet turns
        // from re-hitting the endpoint on every remount.
        if (res.files.length > 0 || cacheEmpty) cacheSummary(key, res);
        if (
          res.files.length === 0 &&
          !cacheEmpty &&
          !summaryRetriedRef.current
        ) {
          // Checkpoints are written after the stream's done chunk; if the
          // first fetch raced that write, retry once shortly after the
          // response lands. Scheduling here (not from a fixed post-settle
          // timer) means a slow first request still gets its retry.
          summaryRetriedRef.current = true;
          summaryRetryTimerRef.current = window.setTimeout(() => {
            summaryRetryTimerRef.current = null;
            void refreshSummary(true);
          }, SUMMARY_RETRY_MS);
        }
        setServerSummary(res);
      } catch {
        // A rejection is a genuine failure: fall back to the client estimate
        // and leave the miss uncached so a remount retries.
        if (requestId !== summaryRequestRef.current) return;
        setServerSummary(null);
      }
    },
    [agentId, threadId, messageId, streaming, canCheckpoint],
  );

  // Fetch the authoritative summary for every settled turn, even when the
  // client estimate is empty: writes made by subagents (or any path the
  // client-side tool scan cannot see) are only known to the server. The
  // settle-race retry is scheduled inside refreshSummary; this effect only
  // cleans its timer up.
  const needsSummary = !streaming && canCheckpoint;
  useEffect(() => {
    if (!needsSummary) {
      // Same invalidation as inside refreshSummary: an in-flight response
      // must not populate state after the turn resumed streaming, and a
      // summary cached during a mid-turn lull (tool/HITL gap) must not be
      // served after the real settle.
      summaryRequestRef.current += 1;
      if (agentId && threadId && messageId) {
        turnSummaryCache.delete(summaryCacheKey(agentId, threadId, messageId));
      }
      setServerSummary(null);
      return undefined;
    }
    void refreshSummary();
    return () => {
      if (summaryRetryTimerRef.current !== null) {
        window.clearTimeout(summaryRetryTimerRef.current);
        summaryRetryTimerRef.current = null;
      }
    };
  }, [needsSummary, refreshSummary]);

  const serverFiles = serverSummary?.files ?? [];
  const useServer = !streaming && serverFiles.length > 0;
  // Server stats are authoritative per checkpointed file, but rows the
  // client estimate detected without a checkpoint (sub-agent writes,
  // editedFiles entries) stay listed instead of silently disappearing.
  const displayFiles: TurnFileChange[] = useMemo(() => {
    if (!useServer) return summary.files;
    // The client's display path and the harness's recorded path can differ in
    // form (absolute vs workspace-relative); canonicalize both before joining.
    const byPath = new Map(
      serverFiles.map((f) => {
        const canonical = canonicalizeDockFilePath(f.path, agentId) || f.path;
        return [canonical, f] as const;
      }),
    );
    const matchStats = (key: string) =>
      byPath.get(key) ??
      [...byPath.entries()].find(([canonical]) =>
        key.endsWith(`/${canonical}`),
      )?.[1];
    const merged: TurnFileChange[] = [];
    const seen = new Set<string>();
    for (const row of summary.files) {
      const rowKey =
        canonicalizeDockFilePath(row.displayPath, row.agentId ?? agentId) ||
        row.displayPath;
      seen.add(rowKey);
      const stats = matchStats(rowKey);
      merged.push(
        stats
          ? {
              ...row,
              checkpointPath: stats.path,
              additions: stats.added,
              deletions: stats.removed,
              measured: true,
            }
          : row,
      );
    }
    for (const stats of serverFiles) {
      const canonical =
        canonicalizeDockFilePath(stats.path, agentId) || stats.path;
      if (!seen.has(canonical)) {
        merged.push({
          openPath: stats.path,
          displayPath: stats.path,
          checkpointPath: stats.path,
          agentId: agentId ?? null,
          additions: stats.added,
          deletions: stats.removed,
          measured: true,
          pending: false,
        });
      }
    }
    return merged;
  }, [useServer, summary, serverFiles, agentId]);
  const additions = displayFiles.reduce(
    (sum, f) => sum + (f.measured ? f.additions : 0),
    0,
  );
  const deletions = displayFiles.reduce(
    (sum, f) => sum + (f.measured ? f.deletions : 0),
    0,
  );
  const measured = additions + deletions > 0;
  const reverted = serverSummary?.reverted === true;

  const openTurnDiff = async (row: TurnFileChange) => {
    // Review shows the turn-scoped diff; the checkpoint is keyed by the
    // harness-recorded path, which can differ in form from the display path.
    const path = row.checkpointPath ?? row.displayPath;
    if (!canCheckpoint) {
      filePreview?.openGitChange(path, agentId);
      return;
    }
    const requestId = ++diffRequestRef.current;
    setDiffPath(path);
    setDiffLoading(true);
    setDiffText("");
    setDiffUnavailable(false);
    try {
      const res = await fileCheckpointsApi.turnDiff(
        agentId!,
        threadId!,
        messageId!,
        path,
      );
      if (requestId !== diffRequestRef.current) return;
      setDiffText(res.diff);
    } catch {
      if (requestId !== diffRequestRef.current) return;
      // No checkpoint for this path (e.g. shell write): never fall back to
      // the git worktree diff — it would show changes this turn did not make.
      setDiffUnavailable(true);
    } finally {
      if (requestId === diffRequestRef.current) setDiffLoading(false);
    }
  };

  const openRewind = async () => {
    if (!canCheckpoint) return;
    setRewindOpen(true);
    setPreviewLoading(true);
    setPreview(null);
    try {
      setPreview(
        await fileCheckpointsApi.rewindPreview(agentId!, threadId!, messageId!),
      );
    } catch (err) {
      message.error(apiErrorMessage(err, t("git.opFailed")));
      setRewindOpen(false);
    } finally {
      setPreviewLoading(false);
    }
  };

  const canApplyPreview = preview?.can_apply === true;

  const applyRewind = async () => {
    if (!canCheckpoint || !canApplyPreview) return;
    setApplying(true);
    try {
      const res = await fileCheckpointsApi.rewindApply(
        agentId!,
        threadId!,
        messageId!,
      );
      const blocked = res.blocked ?? [];
      if (blocked.length > 0) {
        message.warning(t("git.rewindBlocked", { count: blocked.length }));
        setPreview(null);
        void openRewind();
        return;
      }
      message.success(
        t("git.rewindApplied", {
          count: res.applied.length,
          defaultValue: "已回滚 {{count}} 个文件",
        }),
      );
      setRewindOpen(false);
      // Re-read the authoritative stats so the reverted badge appears and
      // the undo action disappears immediately; the cached pre-rewind
      // summary must not shadow the refresh.
      // Restoring this turn also discards files written by later turns,
      // so every cached summary in this thread may be stale.
      const prefix = `${threadId}:`;
      for (const key of [...turnSummaryCache.keys()]) {
        if (key.startsWith(prefix)) turnSummaryCache.delete(key);
      }
      void refreshSummary();
    } catch (err) {
      message.error(apiErrorMessage(err, t("git.opFailed")));
    } finally {
      setApplying(false);
    }
  };

  if (displayFiles.length === 0 && fallbackCount === 0) {
    // Neither source knows about files: render nothing instead of a
    // placeholder with a wrong count. (The pending summary does not hide
    // the fallback button — that would flip the card height twice.)
    return null;
  }

  if (displayFiles.length === 0) {
    return (
      <button
        type="button"
        className={cx(
          styles.openBrowserPrompt,
          streaming && styles.openBrowserPromptActive,
        )}
        onClick={onOpenList}
        aria-label={t("chat.editFileCard", {
          count: Math.max(fallbackCount, 1),
        })}
      >
        <FilePen
          size={16}
          strokeWidth={2}
          className={styles.openBrowserPromptIcon}
          aria-hidden="true"
        />
        <span>
          {t("chat.editFileCard", { count: Math.max(fallbackCount, 1) })}
        </span>
        <ChevronRight
          size={14}
          className={styles.openBrowserPromptArrow}
          aria-hidden="true"
        />
      </button>
    );
  }

  const visible = visibleFileChanges(displayFiles, showAll);
  const moreCount = displayFiles.length - visible.length;
  const summaryText = t("git.filesChanged", {
    count: displayFiles.length,
    defaultValue: "{{count}} 个文件变更",
  });

  return (
    <div className={styles.turnChangeCard} data-testid="turn-change-card">
      <div
        className={cx(
          styles.openBrowserPrompt,
          styles.turnChangeSummary,
          streaming && styles.openBrowserPromptActive,
        )}
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") setExpanded((v) => !v);
        }}
        aria-expanded={expanded}
      >
        <ChevronRight
          size={14}
          className={cx(
            styles.openBrowserPromptArrow,
            expanded && styles.turnChangeChevronOpen,
          )}
          aria-hidden="true"
        />
        <span className={styles.turnChangeSummaryText}>{summaryText}</span>
        {measured && (
          <span className={styles.fileChangeRowStats}>
            <span className={styles.fileChangeAdd}>+{additions}</span>
            <span className={styles.fileChangeDel}>−{deletions}</span>
          </span>
        )}
        {reverted && (
          <span
            className={styles.turnChangeReverted}
            data-testid="turn-change-reverted"
          >
            {t("git.reverted", { defaultValue: "已撤销" })}
          </span>
        )}
        {canCheckpoint && !streaming && !reverted && (
          <button
            type="button"
            className={styles.turnChangeUndo}
            data-testid="turn-undo"
            onClick={(e) => {
              e.stopPropagation();
              void openRewind();
            }}
          >
            <Undo2 size={13} aria-hidden="true" />
            {t("git.undo", "Undo")}
          </button>
        )}
      </div>

      {expanded && (
        <ul className={styles.fileChangeList}>
          {visible.map((file) => {
            const showStats =
              file.measured && file.additions + file.deletions > 0;
            const dir = changeDir(file.displayPath);
            return (
              <li key={`${file.agentId ?? ""} ${file.displayPath}`}>
                <div
                  className={cx(
                    styles.fileChangeRow,
                    streaming && file.pending && styles.openBrowserPromptActive,
                  )}
                  data-testid="turn-change-row"
                >
                  <button
                    type="button"
                    className={styles.fileChangeRowMain}
                    title={file.displayPath}
                    onClick={() => void openTurnDiff(file)}
                  >
                    <FilePen
                      size={16}
                      strokeWidth={2}
                      className={styles.openBrowserPromptIcon}
                      aria-hidden="true"
                    />
                    <span className={styles.fileChangeName}>
                      {fileChangeChipLabel(file.displayPath)}
                    </span>
                    <span className={styles.turnChangeDir}>{dir}</span>
                    {file.pending ? (
                      <span className={styles.fileChangePending}>
                        {t("chat.fileChangePending")}
                      </span>
                    ) : null}
                    {showStats ? (
                      <span className={styles.fileChangeRowStats}>
                        <span className={styles.fileChangeAdd}>
                          +{file.additions}
                        </span>
                        <span className={styles.fileChangeDel}>
                          −{file.deletions}
                        </span>
                      </span>
                    ) : null}
                  </button>
                  <span className={styles.turnChangeRowActions}>
                    <button
                      type="button"
                      className={styles.turnChangeAction}
                      onClick={() => void openTurnDiff(file)}
                    >
                      {t("git.review", "Review")}
                    </button>
                    <button
                      type="button"
                      className={styles.turnChangeAction}
                      onClick={() => {
                        if (filePreview) {
                          filePreview.openFilePreview(
                            file.openPath,
                            file.agentId,
                          );
                        } else {
                          onOpenList?.();
                        }
                      }}
                    >
                      {t("git.open", "打开")}
                    </button>
                  </span>
                </div>
              </li>
            );
          })}
          {moreCount > 0 ? (
            <li>
              <button
                type="button"
                className={cx(styles.openBrowserPrompt, styles.fileChangeRow)}
                onClick={() => setShowAll(true)}
              >
                {t("chat.fileChangeMore", { count: moreCount })}
              </button>
            </li>
          ) : null}
        </ul>
      )}

      <Modal
        title={diffPath ?? undefined}
        className={styles.turnDiffModal}
        open={diffPath != null}
        footer={null}
        width="72vw"
        onCancel={() => setDiffPath(null)}
        destroyOnHidden
      >
        {diffLoading ? (
          <div className={styles.viewerLoading}>
            <Spin />
          </div>
        ) : diffUnavailable ? (
          <div className={styles.turnChangeEmpty}>
            {t("git.diffUnavailable", {
              defaultValue: "暂时无法预览这份 Diff。",
            })}
          </div>
        ) : (
          <GitDiffView diff={diffText} />
        )}
      </Modal>

      <Modal
        title={t("git.rewindTitle", "回滚本轮文件更改")}
        open={rewindOpen}
        onCancel={() => setRewindOpen(false)}
        destroyOnHidden
        footer={
          <div className={styles.turnRewindFooter}>
            <Button onClick={() => setRewindOpen(false)}>
              {t("common.cancel", "取消")}
            </Button>
            <Button
              type="primary"
              danger
              loading={applying}
              disabled={!canApplyPreview}
              onClick={() => void applyRewind()}
            >
              {t("git.rewindApply", "回滚")} ({preview?.safe.length ?? 0})
            </Button>
          </div>
        }
      >
        {previewLoading ? (
          <div className={styles.viewerLoading}>
            <Spin />
          </div>
        ) : preview ? (
          <div className={styles.turnRewindList}>
            <p className={styles.turnRewindHint}>
              {t(
                "git.rewindHint",
                "仅回滚自本轮后未被外部修改的文件；新建文件将被删除。",
              )}
            </p>
            {preview.safe.map((f) => (
              <div key={`s:${f.path}`} className={styles.turnRewindRow}>
                <span className={styles.fileChangeName}>{f.path}</span>
                <span className={styles.turnRewindTagSafe}>
                  {t("git.rewindSafe", "可回滚")}
                </span>
              </div>
            ))}
            {preview.unsafe.map((f) => (
              <div key={`u:${f.path}`} className={styles.turnRewindRow}>
                <span className={styles.fileChangeName}>{f.path}</span>
                <span className={styles.turnRewindTagUnsafe}>
                  {t("git.rewindUnsafe", "已被外部修改")}
                </span>
              </div>
            ))}
            {preview.ignored.map((f) => (
              <div key={`i:${f.path}`} className={styles.turnRewindRow}>
                <span className={styles.fileChangeName}>{f.path}</span>
                <span className={styles.turnRewindTagIgnored}>
                  {t("git.rewindIgnored", { defaultValue: "已忽略" })}
                </span>
              </div>
            ))}
            {preview.safe.length === 0 &&
              preview.unsafe.length === 0 &&
              preview.ignored.length === 0 && (
                <div className={styles.turnChangeEmpty}>
                  {t("git.noChanges")}
                </div>
              )}
            {!canApplyPreview && preview.unsafe.length > 0 && (
              <p className={styles.turnRewindHint}>
                {t("git.rewindCannotApply", {
                  defaultValue:
                    "有文件在本轮之后被修改，无法安全回滚；本次不会写入任何文件。",
                })}
              </p>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}

function visibleFileChanges(
  files: readonly TurnFileChange[],
  showAll: boolean,
): TurnFileChange[] {
  if (showAll || files.length <= FILE_CHANGE_PREVIEW) return [...files];
  const head = files.slice(0, FILE_CHANGE_PREVIEW);
  const pending = files
    .slice(FILE_CHANGE_PREVIEW)
    .filter((file) => file.pending);
  return [...head, ...pending];
}
