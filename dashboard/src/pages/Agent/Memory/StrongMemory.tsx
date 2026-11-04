import { useEffect, useRef, useState } from "react";
import { Alert, Button, Input, Skeleton } from "antd";
import { useTranslation } from "react-i18next";

import memoryApi from "../../../api/modules/memoryDashboard";
import type { ManualMemoryReview } from "../../../api/modules/memoryDashboard";
import { message } from "../../../utils/antdMessage";
import styles from "./StrongMemory.module.less";

const reviewFallbacks: Record<string, string> = {
  complete: "当前核对已完成。",
  partial: "还有 {{count}} 条普通记忆待检查，点击继续核对。",
  uncertain: "部分信息无法确定，原记忆保持不变。请补充明确档案后重新检查。",
  unavailable: "语义检查不可用，尚未完成核对。请配置记忆辅助模型后重试。",
  failed: "核对尚未完成，请稍后重试。",
  stale: "手动文档已变化，请重新核对。",
  disabled: "普通记忆未启用，文档已保存，暂不执行核对。",
  too_large: "文档过长，尚未完成语义检查。请精简后重试。",
  not_checked: "这些手动文档尚未核对。",
};

export default function StrongMemory({
  agentId,
  document = "strong",
  onReviewCandidates,
}: {
  agentId: string;
  document?: "strong" | "user";
  onReviewCandidates?: () => void;
}) {
  const { t } = useTranslation();
  const userFile = document === "user";
  const scope = userFile ? "memory.userFile" : "memory.strong";
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [exists, setExists] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const reviewRequest = useRef(0);
  const [review, setReview] = useState<ManualMemoryReview | null>(null);
  const [reviewing, setReviewing] = useState(false);

  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);
    setSaving(false);
    setFailed(false);
    setContent("");
    setSavedContent("");
    setReview(null);
    setReviewing(false);
    const load = userFile
      ? memoryApi.getUserProfile
      : memoryApi.getStrongMemory;
    load(agentId)
      .then((file) => {
        if (generation.current !== current) return;
        setContent(file.content);
        setSavedContent(file.content);
        setExists(file.exists);
      })
      .catch(() => {
        if (generation.current === current) setFailed(true);
      })
      .finally(() => {
        if (generation.current === current) setLoading(false);
      });
    const reviewCurrent = ++reviewRequest.current;
    memoryApi
      .getManualMemoryReview(agentId)
      .then((result) => {
        if (
          generation.current === current &&
          reviewRequest.current === reviewCurrent
        )
          setReview(result);
      })
      .catch(() => {
        if (
          generation.current === current &&
          reviewRequest.current === reviewCurrent
        )
          setReview({
            status: "failed",
            conflicts: 0,
            duplicates: 0,
            checked: 0,
            remaining: 0,
            candidate_ids: [],
          });
      });
    return () => {
      generation.current = current + 1;
    };
  }, [agentId, document, userFile, retry]);

  const checkSaved = async () => {
    const current = generation.current;
    const reviewCurrent = ++reviewRequest.current;
    setReviewing(true);
    try {
      const result = await memoryApi.reviewManualMemory(agentId);
      if (
        generation.current === current &&
        reviewRequest.current === reviewCurrent
      )
        setReview(result);
    } catch {
      if (
        generation.current === current &&
        reviewRequest.current === reviewCurrent
      )
        setReview({
          status: "failed",
          conflicts: 0,
          duplicates: 0,
          checked: 0,
          remaining: 0,
          candidate_ids: [],
        });
    } finally {
      if (generation.current === current) setReviewing(false);
    }
  };

  const save = async () => {
    const current = generation.current;
    setSaving(true);
    try {
      const put = userFile
        ? memoryApi.putUserProfile
        : memoryApi.putStrongMemory;
      const file = await put(agentId, content);
      if (generation.current !== current) return;
      setSavedContent(file.content);
      setExists(file.exists);
      message.success(
        t(
          `${scope}.saved`,
          userFile
            ? "用户档案已保存，将在新会话中生效。"
            : "强记忆已保存，将在新会话中生效。",
        ),
      );
      void checkSaved();
    } catch {
      if (generation.current === current) {
        message.error(
          t(`${scope}.saveFailed`, "保存失败，修改内容已保留，请重试。"),
        );
      }
    } finally {
      if (generation.current === current) setSaving(false);
    }
  };

  const disabled = loading || failed || saving;
  const reviewStatus = review
    ? t(`memory.manualReview.${review.status}`, {
        count: review.remaining,
        defaultValue: reviewFallbacks[review.status] || reviewFallbacks.failed,
      })
    : "";
  return (
    <div className={styles.strongMemory}>
      <Alert
        type="info"
        showIcon
        message={t(
          `${scope}.contextNotice`,
          userFile
            ? "每个会话开始时加载一次 USER.md 用户档案，并持续用于该会话上下文。"
            : "每个会话开始时加载一次强记忆，并持续用于该会话上下文。",
        )}
        description={t(
          `${scope}.description`,
          userFile
            ? "USER.md 由你手动维护，Agent 只读，适合填写个人信息、称呼和沟通偏好。修改后对新会话生效。与普通记忆冲突时以手动档案为准，冲突记忆转为候选待审核。对 Agent 说“记住”会保存到普通记忆，不会改动这里。"
            : "强记忆由你手动维护，适合填写始终需要参考的重要背景和约定。同一会话内内容保持不变，修改后对新会话生效。普通记忆按需召回，每次将相关记忆加入上下文。对 Agent 说“记住”会保存到普通记忆，不会改动这里。",
        )}
      />
      {review && (
        <Alert
          showIcon
          type={
            review.conflicts > 0 ||
            !["complete", "not_checked"].includes(review.status)
              ? "warning"
              : "info"
          }
          message={
            review.conflicts > 0
              ? t("memory.manualReview.conflicts", {
                  count: review.conflicts,
                  defaultValue: "发现 {{count}} 条冲突，已转为候选待审核。",
                })
              : reviewStatus
          }
          description={
            <>
              {review.conflicts > 0 && review.status !== "complete" && (
                <p>{reviewStatus}</p>
              )}
              {t("memory.manualReview.details", {
                count: review.duplicates,
                defaultValue:
                  "手动文档优先。相同档案快照中的 {{count}} 条重复记忆不再重复注入；已确认的冲突转为候选，旧记忆停用并保留原始证据。核对基于已保存的 USER.md 和 MEMORY.md。",
              })}
            </>
          }
          action={
            review.conflicts > 0 && onReviewCandidates ? (
              <Button onClick={onReviewCandidates}>
                {t("memory.manualReview.openCandidates", "查看候选")}
              </Button>
            ) : undefined
          }
        />
      )}
      {failed && (
        <Alert
          type="error"
          showIcon
          message={t(
            `${scope}.loadFailed`,
            userFile
              ? "加载用户档案失败，请重试。"
              : "加载强记忆失败，请重试。",
          )}
          action={
            <Button onClick={() => setRetry((value) => value + 1)}>
              {t("common.retry", "重试")}
            </Button>
          }
        />
      )}
      {loading ? (
        <Skeleton active paragraph={{ rows: 10 }} />
      ) : (
        <div className={styles.editor}>
          <label htmlFor={`manual-memory-${document}-${agentId}`}>
            {t(
              `${scope}.contentLabel`,
              userFile ? "用户档案内容（USER.md）" : "强记忆内容",
            )}
          </label>
          <Input.TextArea
            id={`manual-memory-${document}-${agentId}`}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            disabled={disabled}
            autoSize={{ minRows: 16, maxRows: 32 }}
            placeholder={t(
              `${scope}.placeholder`,
              userFile
                ? "填写你的个人信息和偏好，支持 Markdown。"
                : "在这里填写每次聊天都需要参考的内容，支持 Markdown。",
            )}
            spellCheck={false}
          />
        </div>
      )}
      <div className={styles.actions}>
        <Button
          loading={reviewing}
          disabled={disabled || content !== savedContent || reviewing}
          onClick={() => void checkSaved()}
        >
          {t("memory.manualReview.check", "检查重复与冲突")}
        </Button>
        <Button
          disabled={disabled || content === savedContent}
          onClick={() => setContent(savedContent)}
        >
          {t("memory.strong.discard", "撤销修改")}
        </Button>
        <Button
          type="primary"
          loading={saving}
          disabled={
            disabled || reviewing || (exists && content === savedContent)
          }
          onClick={save}
        >
          {t("common.save", "保存")}
        </Button>
      </div>
    </div>
  );
}
