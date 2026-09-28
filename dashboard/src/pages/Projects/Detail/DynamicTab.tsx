import { useMemo, useState } from "react";
import { Button, Input, Spin, Typography } from "antd";
import { BadgeCheck, Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import {
  projectsApi,
  type ProjectComment,
} from "../../../api/modules/projects";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { useProjectMembers } from "../../../hooks/useProjectMembers";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "../../../utils/antdMessage";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./DynamicTab.module.less";

const { Text } = Typography;

/**
 * 结论文本 =「结论 · 由 <谁> 采纳」（`P3` 展示形态 / `P3b` 显示口径 / `L30`）。
 *
 * 回退链（**与 `feed-author` 同一条口径**：名字优先 → 回退 → 不空白）：
 *   ① `concluded_by_name`（后端解析好，**直接用**，不自己拼 ✗）
 *   ② 拿不到名字 ⇒ `concluded_by_type:concluded_by_id`（★ **仍能区分「谁」**）
 *   ③ 连 id 都没有 ⇒ `concludedByUnknown`（「已注销用户」，**不得空白**）
 */
function concludedByLabel(
  comment: ProjectComment,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const name = comment.concluded_by_name?.trim();
  if (name) return t("projects.conclusionBy", { name });
  const id = comment.concluded_by_id?.trim();
  if (id) {
    const kind = comment.concluded_by_type?.trim();
    return t("projects.conclusionBy", { name: kind ? `${kind}:${id}` : id });
  }
  return t("projects.concludedByUnknown");
}

/** 与 QuickInput 同一口径的可写角色集（`PROJECT_WRITE`）。 */
const WRITE_ROLES = new Set(["owner", "admin", "member"]);

/**
 * 动态 Tab —— 项目留言 feed（PLAN §1.2 / 批次八 A2）。
 *
 * 结构（逐字）：`feed-composer`（textarea + 发布）→ `feed-list`/`feed-item`
 * （作者 / 时间（**服务器时区**格式化）/ 正文 / **结论徽标**）→ 空态 `feed-empty`。
 *
 * ★ `dynamicPlaceholder`/`dynamicComingSoon` **保留为键但不再渲染**（`PLAN §9 O4`）。
 * ★ 本批**不做**（`O3`）：与我相关 / 成员动态 / 嵌套回复 / 通知 / 附件 / 编辑删除。
 * ★ 作者由**服务端**按登录身份判定（`CommentCreate` 无作者字段）⇒ 前端无作者选择器。
 */
function DynamicTab() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const { projectId = "" } = useParams<{ projectId: string }>();
  const currentUser = useCurrentUser();
  const { members, loading: membersLoading } = useProjectMembers(projectId);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  /** 正在编辑的留言 id（null = 无）与其草稿。 */
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingBody, setEditingBody] = useState("");

  const {
    data: comments,
    loading,
    refresh,
  } = useAsyncResource<ProjectComment[]>(
    [],
    () => projectsApi.listComments(projectId),
    [projectId],
    {
      enabled: projectId !== "",
      errorFallback: t("projects.loadFailed"),
      t,
      logLabel: "project-feed",
    },
  );

  /** UX 门（服务端仍在）：`viewer` 不渲染写入口。 */
  const canWrite = useMemo(() => {
    if (currentUser?.id === undefined) return false;
    const mine = members.find(
      (member) =>
        member.subject_type === "user" && member.user_id === currentUser.id,
    );
    return mine ? WRITE_ROLES.has(mine.role) : false;
  }, [currentUser, members]);

  const publish = async () => {
    const body = draft.trim();
    if (!body || saving) return;
    setSaving(true);
    try {
      await projectsApi.createComment(projectId, { body });
      setDraft("");
      await refresh();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.feedPost"), t));
    } finally {
      setSaving(false);
    }
  };

  const toggleConclusion = async (comment: ProjectComment) => {
    try {
      if (comment.concluded) {
        await projectsApi.unconcludeComment(projectId, comment.comment_id);
      } else {
        await projectsApi.concludeComment(projectId, comment.comment_id);
      }
      await refresh();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.conclude"), t));
    }
  };

  /** 编辑保存（`PATCH …/comments/{cid}`）。 */
  const saveEdit = async (commentId: string) => {
    const next = editingBody.trim();
    if (!next) return;
    try {
      await projectsApi.updateComment(projectId, commentId, next);
      setEditingId(null);
      setEditingBody("");
      await refresh();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.loadFailed"), t));
    }
  };

  /** 硬删（`DELETE …/comments/{cid}`）。★ 已采纳留言**事前禁用**入口（服务端另有 409 兜底）。 */
  const removeComment = async (commentId: string) => {
    try {
      await projectsApi.deleteComment(projectId, commentId);
      await refresh();
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("apiErrors.PROJECT_COMMENT_CONCLUDED"), t),
      );
    }
  };

  /** 附件挂载：先暂存（`POST …/attachments`），再绑到该留言（`PATCH …/attachments/{id}`）。 */
  const attachToComment = async (commentId: string, file: File) => {
    try {
      const staged = await projectsApi.uploadStagedAttachment(projectId, file);
      await projectsApi.bindAttachment(projectId, staged.artifact_id, {
        commentId,
      });
      await refresh();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.loadFailed"), t));
    }
  };

  const roleKnown = !membersLoading;

  return (
    <div className={styles.wrapper} data-testid="project-dynamic">
      {roleKnown && canWrite ? (
        <div className={styles.composer} data-testid="feed-composer">
          <Input.TextArea
            className={styles.composerInput}
            value={draft}
            autoSize={{ minRows: 1, maxRows: 4 }}
            placeholder={t("projects.feedComposerPlaceholder")}
            aria-label={t("projects.feedComposerPlaceholder")}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button
            type="primary"
            icon={<Send size={14} />}
            loading={saving}
            disabled={draft.trim().length === 0}
            onClick={() => void publish()}
          >
            {t("projects.feedPost")}
          </Button>
        </div>
      ) : null}

      {loading && comments.length === 0 ? (
        <div className={styles.centered}>
          <Spin size="small" />
        </div>
      ) : comments.length === 0 ? (
        <Text type="secondary" data-testid="feed-empty">
          {t("projects.feedEmpty")}
        </Text>
      ) : (
        <ul className={styles.list} data-testid="feed-list">
          {comments.map((comment) => (
            <li
              key={comment.comment_id}
              className={styles.item}
              data-testid="feed-item"
            >
              <div className={styles.itemHead}>
                <span className={styles.author} data-testid="feed-author">
                  {/* 显示名优先；拿不到 ⇒ 回退 `type:id`（**不得空白**，与成员行同口径）。 */}
                  {comment.name?.trim()
                    ? comment.name
                    : `${comment.author_type}:${comment.author_id}`}
                </span>
                <span className={styles.time}>
                  {formatServerDateTime(comment.created_at, timeZone)}
                </span>
                {comment.concluded ? (
                  <span
                    className={styles.badge}
                    data-testid="comment-conclusion-badge"
                  >
                    <BadgeCheck size={13} aria-hidden />
                    {t("projects.conclusionBadge")}
                  </span>
                ) : null}
                {comment.concluded ? (
                  <span
                    className={styles.concludedBy}
                    data-testid="comment-conclusion-by"
                  >
                    {concludedByLabel(comment, t)}
                  </span>
                ) : null}
              </div>
              {editingId === comment.comment_id ? (
                <div className={styles.editRow}>
                  <Input.TextArea
                    className={styles.composerInput}
                    value={editingBody}
                    autoSize={{ minRows: 1, maxRows: 6 }}
                    aria-label={t("projects.feedPost")}
                    data-testid="comment-edit-input"
                    onChange={(event) => setEditingBody(event.target.value)}
                  />
                  <Button
                    size="small"
                    type="primary"
                    data-testid="comment-edit-save"
                    onClick={() => void saveEdit(comment.comment_id)}
                  >
                    {t("projects.feedPost")}
                  </Button>
                  <Button
                    size="small"
                    data-testid="comment-edit-cancel"
                    onClick={() => setEditingId(null)}
                  >
                    {t("common.cancel", "取消")}
                  </Button>
                </div>
              ) : (
                <div className={styles.body}>{comment.body}</div>
              )}
              {canWrite ? (
                <div className={styles.actions}>
                  <Button
                    type="link"
                    size="small"
                    className={styles.concludeAction}
                    onClick={() => void toggleConclusion(comment)}
                  >
                    {comment.concluded
                      ? t("projects.unconclude")
                      : t("projects.conclude")}
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    data-testid="comment-edit"
                    onClick={() => {
                      setEditingId(comment.comment_id);
                      setEditingBody(comment.body);
                    }}
                  >
                    {t("common.edit", "编辑")}
                  </Button>
                  {comment.concluded ? (
                    <>
                      {/* ★ 与后端**同一口径**：已采纳 ⇒ 删除【事前禁用】，提示用**同一个键**
                          （`apiErrors.PROJECT_COMMENT_CONCLUDED`，与 409 的 message 同源）。 */}
                      <Button
                        type="link"
                        size="small"
                        disabled
                        data-testid="comment-delete"
                      >
                        {t("common.delete", "删除")}
                      </Button>
                      <span
                        className={styles.blockedHint}
                        data-testid="comment-delete-blocked"
                      >
                        {t("apiErrors.PROJECT_COMMENT_CONCLUDED")}
                      </span>
                    </>
                  ) : (
                    <Button
                      type="link"
                      size="small"
                      data-testid="comment-delete"
                      onClick={() => void removeComment(comment.comment_id)}
                    >
                      {t("common.delete", "删除")}
                    </Button>
                  )}
                  <label className={styles.attachLabel}>
                    <input
                      type="file"
                      className={styles.attachInput}
                      data-testid="comment-attachment-input"
                      aria-label={t("projects.attachFile")}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file)
                          void attachToComment(comment.comment_id, file);
                        event.target.value = "";
                      }}
                    />
                    <span data-testid="comment-attach">
                      {t("projects.feedPost")}
                    </span>
                  </label>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default DynamicTab;
