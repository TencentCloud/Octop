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
              </div>
              <div className={styles.body}>{comment.body}</div>
              {canWrite ? (
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
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default DynamicTab;
