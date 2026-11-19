import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, FilePen, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { App, Button, Modal, Spin } from "antd";
import cx from "classnames";
import { useChatFilePreview } from "../ChatFilePreviewContext";
import { isWriteToolName } from "../constants";
import { collectChatFilePaths } from "../hooks/useChatFileDetection";
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
    const fromPaths = collectChatFilePaths(messages, agentId).length;
    if (fromPaths > 0) return fromPaths;
    return messages.filter((m) => isWriteToolName(m.toolData?.name)).length;
  }, [messages, agentId]);

  const messageId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return null;
  }, [messages]);

  const canCheckpoint = Boolean(agentId && threadId && messageId);
  const diffRequestRef = useRef(0);

  const summaryRequestRef = useRef(0);
  const refreshSummary = useCallback(async () => {
    if (!canCheckpoint || streaming) {
      // Invalidate any in-flight summary so a late response cannot
      // repopulate serverSummary after the card fell back to the estimate.
      summaryRequestRef.current += 1;
      setServerSummary(null);
      return;
    }
    const requestId = ++summaryRequestRef.current;
    try {
      const res = await fileCheckpointsApi.turnSummary(
        agentId!,
        threadId!,
        messageId!,
      );
      if (requestId === summaryRequestRef.current) setServerSummary(res);
    } catch {
      // No checkpoints (older harness) or transient failure: fall back to
      // the client estimate instead of showing stale authoritative stats.
      if (requestId === summaryRequestRef.current) setServerSummary(null);
    }
  }, [agentId, threadId, messageId, streaming, canCheckpoint]);

  // Only turns whose client estimate saw write/edit tools can have
  // checkpoints — skip the request for every other historical turn.
  const needsSummary = !streaming && canCheckpoint && summary.files.length > 0;
  useEffect(() => {
    if (!needsSummary) {
      setServerSummary(null);
      return;
    }
    void refreshSummary();
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
      // the undo action disappears immediately.
      void refreshSummary();
    } catch (err) {
      message.error(apiErrorMessage(err, t("git.opFailed")));
    } finally {
      setApplying(false);
    }
  };

  if (summary.files.length === 0) {
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
