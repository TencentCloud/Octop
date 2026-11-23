/**
 * GitChangeList — grouped change rows (staged / changes / untracked) shared
 * by the standalone git panel. Row click selects the file; actions stage,
 * unstage or discard with confirmation.
 */

import { Popconfirm, Tooltip } from "antd";
import { Plus, RotateCcw, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { GitFileChange, GitStatus } from "../../../api/modules/git";
import { GIT_STATUS_LETTER } from "../../Agent/Workspace/components/gitStatus";
import styles from "../../Agent/Workspace/index.module.less";

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

export function fileBasename(path: string): string {
  return path.split("/").filter(Boolean).pop() || path;
}

export function fileParent(path: string): string {
  const parts = path.replace(/\/+$/, "").split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

interface ChangeRowProps {
  change: GitFileChange;
  streaming: boolean;
  selected?: boolean;
  onSelect: (path: string, staged: boolean) => void;
  onOpenFile: (path: string) => void;
  onStage: (path: string) => void;
  onUnstage: (path: string) => void;
  onDiscard: (path: string) => void;
}

function ChangeRow({
  change,
  streaming,
  selected = false,
  onSelect,
  onOpenFile,
  onStage,
  onUnstage,
  onDiscard,
}: ChangeRowProps) {
  const { t } = useTranslation();
  const letter = GIT_STATUS_LETTER[change.status] ?? "M";
  const modifier = letter === "!" ? "X" : letter;
  const parent = fileParent(change.path);
  return (
    <div
      className={`${styles.gitRow} ${
        selected ? styles.gitRowSelected ?? "" : ""
      }`}
      data-testid="git-change-row"
      data-path={change.path}
      data-staged={change.staged ? "true" : "false"}
      onClick={() => onSelect(change.path, change.staged)}
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

export interface GitChangeListProps {
  status: GitStatus;
  streaming?: boolean;
  selectedPath?: string | null;
  selectedStaged?: boolean;
  onSelect: (path: string, staged: boolean) => void;
  onOpenFile: (path: string) => void;
  onStage: (path: string) => void;
  onUnstage: (path: string) => void;
  onDiscard: (path: string) => void;
}

export default function GitChangeList({
  status,
  streaming = false,
  selectedPath = null,
  selectedStaged = false,
  onSelect,
  onOpenFile,
  onStage,
  onUnstage,
  onDiscard,
}: GitChangeListProps) {
  const { t } = useTranslation();
  const files = status.files;
  const stagedFiles = files.filter((f) => f.staged);
  const unstagedFiles = files.filter(
    (f) => !f.staged && f.status !== "untracked",
  );
  const untrackedFiles = files.filter(
    (f) => !f.staged && f.status === "untracked",
  );

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
            selected={
              change.path === selectedPath && change.staged === selectedStaged
            }
            onSelect={onSelect}
            onOpenFile={onOpenFile}
            onStage={onStage}
            onUnstage={onUnstage}
            onDiscard={onDiscard}
          />
        ))}
      </div>
    );
  };

  if (!files.length) {
    return (
      <div className={styles.gitEmpty} data-testid="git-empty">
        {t("git.noChanges", "没有未提交的更改")}
      </div>
    );
  }

  return (
    <div data-testid="git-change-list">
      {renderGroup(
        t("git.stagedGroup", { count: stagedFiles.length }),
        stagedFiles,
      )}
      {renderGroup(
        t("git.changesGroup", { count: unstagedFiles.length }),
        unstagedFiles,
      )}
      {renderGroup(
        t("git.untrackedGroup", { count: untrackedFiles.length }),
        untrackedFiles,
      )}
    </div>
  );
}
