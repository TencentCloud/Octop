/**
 * Commit dialog — ZCode-style action list: Commit / Commit and push / Push.
 * An empty message is generated from the pending diffs by the host model.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { App, Button, Checkbox, Input, Modal, Tooltip } from "antd";
import {
  Check,
  CloudUpload,
  GitBranch,
  GitCommitHorizontal,
  LoaderCircle,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { gitApi, type GitStatus } from "../../../api/modules/git";
import { apiErrorMessage } from "../../../utils/apiError";
import styles from "../../Agent/Workspace/index.module.less";

interface GitCommitDialogProps {
  open: boolean;
  agentId: string;
  status: GitStatus;
  streaming?: boolean;
  onClose: () => void;
  /** Called after a successful commit or push so the panel can refresh. */
  onDone: () => void;
}

export default function GitCommitDialog({
  open,
  agentId,
  status,
  streaming = false,
  onClose,
  onDone,
}: GitCommitDialogProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [text, setText] = useState("");
  const [includeUnstaged, setIncludeUnstaged] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [busy, setBusy] = useState<"commit" | "commitAndPush" | "push" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setText("");
    setIncludeUnstaged(true);
    setError(null);
    setBusy(null);
    setGenerating(false);
  }, [open]);

  const stagedCount = useMemo(
    () => status.files.filter((file) => file.staged).length,
    [status.files],
  );
  const selectedCount = includeUnstaged ? status.files.length : stagedCount;
  const canCommit = selectedCount > 0 && !streaming;

  const generate = useCallback(async (): Promise<string | null> => {
    setGenerating(true);
    setError(null);
    try {
      const result = await gitApi.generateMessage(agentId, includeUnstaged);
      setText(result.message);
      return result.message;
    } catch (err: unknown) {
      setError(apiErrorMessage(err, t("git.opFailed", "Git 操作失败")));
      return null;
    } finally {
      setGenerating(false);
    }
  }, [agentId, includeUnstaged, t]);

  const submit = useCallback(
    async (push: boolean) => {
      if (!canCommit) return;
      const action = push ? "commitAndPush" : "commit";
      setBusy(action);
      setError(null);
      try {
        let outgoing = text.trim();
        if (!outgoing) {
          const generated = await generate();
          if (!generated) return;
          outgoing = generated;
        }
        const result = await gitApi.commitAdvanced(agentId, {
          message: outgoing,
          include_unstaged: includeUnstaged,
          push,
        });
        message.success(
          result.pushed
            ? t("git.commitDialog.committedAndPushed", {
                commit: result.commit,
                defaultValue: "已提交并推送 {{commit}}",
              })
            : t("git.commitDialog.committed", {
                commit: result.commit,
                defaultValue: "已提交 {{commit}}",
              }),
        );
        onDone();
        onClose();
      } catch (err: unknown) {
        setError(apiErrorMessage(err, t("git.opFailed", "Git 操作失败")));
      } finally {
        setBusy(null);
      }
    },
    [
      agentId,
      canCommit,
      generate,
      includeUnstaged,
      message,
      onClose,
      onDone,
      t,
      text,
    ],
  );

  const pushOnly = useCallback(async () => {
    setBusy("push");
    setError(null);
    try {
      const result = await gitApi.push(agentId);
      message.success(
        t("git.commitDialog.pushed", {
          branch: result.branch,
          defaultValue: "已推送 {{branch}}",
        }),
      );
      onDone();
      onClose();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, t("git.opFailed", "Git 操作失败")));
    } finally {
      setBusy(null);
    }
  }, [agentId, message, onClose, onDone, t]);

  const actionDisabled = busy !== null || generating || streaming;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
      destroyOnHidden
      className={styles.gitCommitDialog}
      data-testid="git-commit-dialog"
    >
      <div className={styles.gitCommitDialogHead}>
        <span className={styles.gitBranchChip}>
          <GitBranch size={12} aria-hidden /> {status.branch ?? "—"}
        </span>
        <span className={styles.gitCommitTotals}>
          <span className={styles.gitRowAdded}>+{status.added}</span>{" "}
          <span className={styles.gitRowRemoved}>−{status.removed}</span>
        </span>
      </div>

      <div className={styles.gitCommitMessageWrap}>
        <Input.TextArea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={t(
            "git.commitDialog.placeholder",
            "Commit message（留空自动生成）",
          )}
          autoSize={{ minRows: 4, maxRows: 8 }}
          disabled={actionDisabled}
          data-testid="git-commit-dialog-input"
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              void submit(false);
            }
          }}
        />
        <Tooltip
          title={
            text.trim()
              ? t("git.commitDialog.regenerate", "重新生成")
              : t("git.commitDialog.generate", "生成提交信息")
          }
        >
          <Button
            type="text"
            size="small"
            className={styles.gitCommitGenerate}
            loading={generating}
            disabled={actionDisabled || selectedCount === 0}
            onClick={() => void generate()}
            aria-label={t("git.commitDialog.generate", "生成提交信息")}
            data-testid="git-commit-generate"
            icon={<Sparkles size={14} />}
          />
        </Tooltip>
      </div>

      <label className={styles.gitCommitInclude}>
        <Checkbox
          checked={includeUnstaged}
          disabled={actionDisabled || stagedCount === status.files.length}
          onChange={(event) => setIncludeUnstaged(event.target.checked)}
          data-testid="git-commit-include-unstaged"
        />
        <span>{t("git.commitDialog.includeUnstaged", "包含未暂存的更改")}</span>
        <span className={styles.gitCommitIncludeCount}>
          {t("git.commitDialog.fileCount", {
            count: selectedCount,
            defaultValue: "{{count}} 个文件",
          })}
        </span>
      </label>

      {error && (
        <div className={styles.gitNotice} data-testid="git-commit-error">
          {error}
        </div>
      )}

      <div className={styles.gitCommitActions}>
        <button
          type="button"
          className={styles.gitCommitAction}
          disabled={actionDisabled || !canCommit}
          onClick={() => void submit(false)}
          data-testid="git-action-commit"
        >
          <span className={styles.gitCommitActionIcon}>
            {busy === "commit" ? (
              <LoaderCircle size={15} className={styles.gitSpin} />
            ) : (
              <GitCommitHorizontal size={15} />
            )}
          </span>
          <span>{t("git.commitDialog.commit", "提交")}</span>
          <kbd className={styles.gitCommitKbd}>⌘⏎</kbd>
        </button>
        <button
          type="button"
          className={styles.gitCommitAction}
          disabled={actionDisabled || !canCommit}
          onClick={() => void submit(true)}
          data-testid="git-action-commit-push"
        >
          <span className={styles.gitCommitActionIcon}>
            {busy === "commitAndPush" ? (
              <LoaderCircle size={15} className={styles.gitSpin} />
            ) : (
              <CloudUpload size={15} />
            )}
          </span>
          <span>{t("git.commitDialog.commitAndPush", "提交并推送")}</span>
        </button>
        <button
          type="button"
          className={styles.gitCommitAction}
          disabled={actionDisabled}
          onClick={() => void pushOnly()}
          data-testid="git-action-push"
        >
          <span className={styles.gitCommitActionIcon}>
            {busy === "push" ? (
              <LoaderCircle size={15} className={styles.gitSpin} />
            ) : (
              <CloudUpload size={15} />
            )}
          </span>
          <span>{t("git.commitDialog.push", "推送")}</span>
        </button>
      </div>

      <div className={styles.gitCommitHint}>
        <Check size={12} aria-hidden />{" "}
        {t(
          "git.commitDialog.hint",
          "空消息会根据本轮 diff 自动生成 Conventional Commit",
        )}
      </div>
    </Modal>
  );
}
