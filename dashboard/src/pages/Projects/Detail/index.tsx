import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  DatePicker,
  Descriptions,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import { Pencil, RefreshCw, Trash2, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import {
  projectsApi,
  type ProjectMember,
  type ProjectMemberRole,
  type ProjectOut,
  type ProjectStatus,
  type ProjectSubjectType,
  type ProjectTask,
  type ProjectUpdateBody,
} from "../../../api/modules/projects";
import { EmptyState } from "../../../components/EmptyState";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import PageShell from "../../../layouts/PageShell";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "../../../utils/antdMessage";
import { showConfirmModal } from "../../../utils/confirmModal";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import Board from "./Board";
import CustomFieldsPanel from "./CustomFieldsPanel";
import styles from "./index.module.less";
import TagsManager from "./TagsManager";

const { Text } = Typography;

const STATUS_LABEL_KEYS: Record<ProjectStatus, string> = {
  draft: "projects.statusDraft",
  active: "projects.statusActive",
  paused: "projects.statusPaused",
  completed: "projects.statusCompleted",
  cancelled: "projects.statusCancelled",
  archived: "projects.statusArchived",
};

const STATUS_COLORS: Record<ProjectStatus, string> = {
  draft: "default",
  active: "success",
  paused: "warning",
  completed: "blue",
  cancelled: "error",
  archived: "default",
};

/**
 * Mirrors `_TRANSITIONS` in `infra/projects/service.py` (PLAN §3.1; ``archived``
 * is terminal, ``completed``/``cancelled`` can reopen as ``active``). The
 * backend stays authoritative and answers an illegal move with
 * `PROJECT_STATUS_INVALID`.
 */
const STATUS_TRANSITIONS: Record<ProjectStatus, ProjectStatus[]> = {
  draft: ["active", "cancelled"],
  active: ["paused", "completed", "cancelled", "archived"],
  paused: ["active", "completed", "cancelled", "archived"],
  completed: ["active", "archived"],
  cancelled: ["active", "archived"],
  archived: [],
};

const ROLE_LABEL_KEYS: Record<ProjectMemberRole, string> = {
  owner: "projects.roleOwner",
  admin: "projects.roleAdmin",
  member: "projects.roleMember",
  viewer: "projects.roleViewer",
};

const SUBJECT_LABEL_KEYS: Record<ProjectSubjectType, string> = {
  user: "projects.subjectUser",
  agent: "projects.subjectAgent",
  team: "projects.subjectTeam",
};

const SUBJECT_ID_HINT_KEYS: Record<ProjectSubjectType, string> = {
  user: "projects.subjectIdHintUser",
  agent: "projects.subjectIdHintAgent",
  team: "projects.subjectIdHintTeam",
};

interface ProjectFormValues {
  name: string;
  goal?: string;
  status: ProjectStatus;
  start_at?: Dayjs | null;
  due_at?: Dayjs | null;
}

interface MemberFormValues {
  subject_type: ProjectSubjectType;
  subject_id: string;
  role: ProjectMemberRole;
}

function memberKey(member: ProjectMember): string {
  return `${member.subject_type}:${member.subject_id}`;
}

function ProjectDetailPage() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const timeZone = useServerTimezone();
  const currentUser = useCurrentUser();
  const [editForm] = Form.useForm<ProjectFormValues>();
  const [memberForm] = Form.useForm<MemberFormValues>();
  const memberSubjectType = Form.useWatch("subject_type", memberForm) ?? "user";

  const [project, setProject] = useState<ProjectOut | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const loadedOnceRef = useRef(false);

  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [memberSaving, setMemberSaving] = useState(false);
  const [roleSavingKey, setRoleSavingKey] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [nextProject, nextMembers, nextTasks] = await Promise.all([
        projectsApi.get(projectId),
        projectsApi.listMembers(projectId),
        projectsApi.listTasks(projectId),
      ]);
      setProject(nextProject);
      setMembers(nextMembers);
      setTasks(nextTasks);
      setLoadError(null);
      loadedOnceRef.current = true;
    } catch (error) {
      setLoadError(error);
      // A failed refresh keeps the previous data on screen; tell the user.
      if (loadedOnceRef.current) {
        message.error(apiErrorMessage(error, t("projects.loadFailed"), t));
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const myMembership = members.find(
    (member) =>
      member.subject_type === "user" &&
      member.user_id !== null &&
      member.user_id === currentUser?.id,
  );
  const myRole = myMembership?.role ?? null;
  const isArchived = project?.status === "archived";
  const canEdit =
    !isArchived &&
    (myRole === "owner" || myRole === "admin" || myRole === "member");
  const canArchive = !isArchived && myRole === "owner";
  const canManageMembers =
    !isArchived && (myRole === "owner" || myRole === "admin");

  const isOwnerMember = useCallback(
    (member: ProjectMember) =>
      member.subject_type === "user" &&
      project !== null &&
      member.subject_id === String(project.owner_user_id),
    [project],
  );

  const openEdit = () => {
    if (!project) return;
    editForm.setFieldsValue({
      name: project.name,
      goal: project.goal,
      status: project.status,
      start_at: project.start_at ? dayjs(project.start_at * 1000) : null,
      due_at: project.due_at ? dayjs(project.due_at * 1000) : null,
    });
    setEditOpen(true);
  };

  const closeEdit = () => {
    setEditOpen(false);
    editForm.resetFields();
  };

  const submitEdit = async (values: ProjectFormValues) => {
    if (!project) return;
    const body: ProjectUpdateBody = {
      name: values.name.trim(),
      goal: values.goal?.trim() ?? "",
      start_at: values.start_at ? values.start_at.unix() : null,
      due_at: values.due_at ? values.due_at.unix() : null,
      clear_start_at: !values.start_at,
      clear_due_at: !values.due_at,
    };
    // Re-sending the current status is not a legal state-machine move.
    if (values.status !== project.status) body.status = values.status;
    setSaving(true);
    try {
      await projectsApi.update(project.project_id, body);
      message.success(t("projects.updated"));
      closeEdit();
      await load();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.updateFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const confirmArchive = () => {
    if (!project) return;
    showConfirmModal({
      title: t("projects.archiveConfirmTitle"),
      content: t("projects.archiveConfirmDesc"),
      okText: t("projects.archive"),
      okType: "danger",
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await projectsApi.archive(project.project_id);
          message.success(t("projects.archived"));
          await load();
        } catch (error) {
          message.error(apiErrorMessage(error, t("projects.archiveFailed"), t));
        }
      },
    });
  };

  const submitMember = async (values: MemberFormValues) => {
    if (!project) return;
    setMemberSaving(true);
    try {
      await projectsApi.addMember(project.project_id, {
        subject_type: values.subject_type,
        subject_id: values.subject_id.trim(),
        role: values.role,
      });
      message.success(t("projects.memberSaved"));
      memberForm.resetFields();
      await load();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.memberSaveFailed"), t));
    } finally {
      setMemberSaving(false);
    }
  };

  const changeRole = async (member: ProjectMember, role: ProjectMemberRole) => {
    if (!project) return;
    setRoleSavingKey(memberKey(member));
    try {
      await projectsApi.addMember(project.project_id, {
        subject_type: member.subject_type,
        subject_id: member.subject_id,
        role,
      });
      message.success(t("projects.memberRoleUpdated"));
      await load();
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.memberSaveFailed"), t));
    } finally {
      setRoleSavingKey(null);
    }
  };

  const confirmRemoveMember = (member: ProjectMember) => {
    if (!project) return;
    showConfirmModal({
      title: t("projects.memberRemoveConfirm"),
      okText: t("common.delete"),
      okType: "danger",
      cancelText: t("common.cancel"),
      onOk: async () => {
        try {
          await projectsApi.removeMember(
            project.project_id,
            member.subject_type,
            member.subject_id,
          );
          message.success(t("projects.memberRemoved"));
          await load();
        } catch (error) {
          message.error(
            apiErrorMessage(error, t("projects.memberRemoveFailed"), t),
          );
        }
      },
    });
  };

  const memberColumns: ColumnsType<ProjectMember> = [
    {
      title: t("projects.memberSubject"),
      key: "subject",
      render: (_, member) => (
        <Space direction="vertical" size={0}>
          <Text className={styles.mono}>{member.subject_id}</Text>
          <Text type="secondary" className={styles.memberSubjectType}>
            {t(SUBJECT_LABEL_KEYS[member.subject_type])}
          </Text>
        </Space>
      ),
    },
    {
      title: t("projects.memberRole"),
      key: "role",
      width: 160,
      render: (_, member) =>
        isOwnerMember(member) ? (
          <Tag color="gold">{t(ROLE_LABEL_KEYS[member.role])}</Tag>
        ) : (
          <Select<ProjectMemberRole>
            size="small"
            value={member.role}
            disabled={!canManageMembers}
            loading={roleSavingKey === memberKey(member)}
            className={styles.roleSelect}
            onChange={(role) => void changeRole(member, role)}
            options={(Object.keys(ROLE_LABEL_KEYS) as ProjectMemberRole[]).map(
              (role) => ({ value: role, label: t(ROLE_LABEL_KEYS[role]) }),
            )}
          />
        ),
    },
    {
      title: t("projects.memberSince"),
      key: "created_at",
      width: 200,
      render: (_, member) => formatServerDateTime(member.created_at, timeZone),
    },
    {
      title: t("common.actions"),
      key: "actions",
      width: 80,
      align: "right",
      render: (_, member) => (
        <Tooltip title={t("common.delete")}>
          <Button
            type="text"
            size="small"
            danger
            disabled={!canManageMembers || isOwnerMember(member)}
            aria-label={t("common.delete")}
            icon={<Trash2 size={14} />}
            onClick={() => confirmRemoveMember(member)}
          />
        </Tooltip>
      ),
    },
  ];

  const headerActions = (
    <Space>
      <Tooltip title={t("common.refresh")}>
        <Button
          icon={<RefreshCw size={15} />}
          loading={loading}
          onClick={() => void load()}
        />
      </Tooltip>
      {project && canEdit ? (
        <Button icon={<Pencil size={15} />} onClick={openEdit}>
          {t("common.edit")}
        </Button>
      ) : null}
      {project && canArchive ? (
        <Button danger onClick={confirmArchive}>
          {t("projects.archive")}
        </Button>
      ) : null}
    </Space>
  );

  if (!project) {
    return (
      <PageShell
        title={t("projects.title")}
        subtitle={t("projects.detailSubtitle")}
      >
        {loading ? (
          <div className={styles.centered}>
            <Spin />
          </div>
        ) : (
          <EmptyState
            variant="error"
            title={t("projects.unavailable")}
            description={apiErrorMessage(
              loadError,
              t("projects.loadFailed"),
              t,
            )}
            actionLabel={t("projects.backToList")}
            onAction={() => navigate("/projects")}
          />
        )}
      </PageShell>
    );
  }

  return (
    <PageShell
      title={project.name}
      subtitle={t("projects.detailSubtitle")}
      actions={headerActions}
    >
      <section className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("projects.overview")}
          <Tag color={STATUS_COLORS[project.status]}>
            {t(STATUS_LABEL_KEYS[project.status])}
          </Tag>
        </div>
        <Descriptions column={1} size="small">
          <Descriptions.Item label={t("projects.goal")}>
            {project.goal || t("projects.noGoal")}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.projectId")}>
            <Text copyable className={styles.mono}>
              {project.project_id}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.kbId")}>
            {project.kb_id ? (
              <Text copyable className={styles.mono}>
                {project.kb_id}
              </Text>
            ) : (
              "—"
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.startAt")}>
            {formatServerDateTime(project.start_at ?? 0, timeZone)}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.dueAt")}>
            {formatServerDateTime(project.due_at ?? 0, timeZone)}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.owner")}>
            {project.owner_user_id}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.createdAt")}>
            {formatServerDateTime(project.created_at, timeZone)}
          </Descriptions.Item>
          <Descriptions.Item label={t("projects.updatedAt")}>
            {formatServerDateTime(project.updated_at, timeZone)}
          </Descriptions.Item>
        </Descriptions>
      </section>

      {/* Project metadata: tag definitions (PLAN §4) and custom-field
          definitions (PLAN §6, ring ④). Both panels own their own section
          shell; this page only mounts them. */}
      <TagsManager projectId={project.project_id} canEdit={canEdit} />
      <CustomFieldsPanel projectId={project.project_id} canEdit={canEdit} />

      <section className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("projects.members")}
          <Text type="secondary" className={styles.sectionHint}>
            {t("projects.membersHint")}
          </Text>
        </div>
        {canManageMembers ? (
          <Form
            form={memberForm}
            layout="inline"
            className={styles.memberForm}
            initialValues={{ subject_type: "user", role: "member" }}
            onFinish={(values) => void submitMember(values)}
          >
            <Form.Item name="subject_type" label={t("projects.memberSubject")}>
              <Select<ProjectSubjectType>
                className={styles.subjectTypeSelect}
                options={(
                  Object.keys(SUBJECT_LABEL_KEYS) as ProjectSubjectType[]
                ).map((type) => ({
                  value: type,
                  label: t(SUBJECT_LABEL_KEYS[type]),
                }))}
              />
            </Form.Item>
            <Form.Item
              name="subject_id"
              label={t("projects.memberId")}
              rules={[
                { required: true, message: t("projects.memberIdRequired") },
              ]}
            >
              <Input
                className={styles.subjectIdInput}
                placeholder={t(SUBJECT_ID_HINT_KEYS[memberSubjectType])}
              />
            </Form.Item>
            <Form.Item name="role" label={t("projects.memberRole")}>
              <Select<ProjectMemberRole>
                className={styles.roleSelect}
                options={(
                  Object.keys(ROLE_LABEL_KEYS) as ProjectMemberRole[]
                ).map((role) => ({
                  value: role,
                  label: t(ROLE_LABEL_KEYS[role]),
                }))}
              />
            </Form.Item>
            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                icon={<UserPlus size={15} />}
                loading={memberSaving}
              >
                {t("projects.memberAdd")}
              </Button>
            </Form.Item>
          </Form>
        ) : null}
        <Table<ProjectMember>
          rowKey={memberKey}
          size="small"
          className={styles.table}
          columns={memberColumns}
          dataSource={members}
          pagination={false}
          scroll={{ x: 640 }}
          locale={{ emptyText: t("projects.membersEmpty") }}
        />
      </section>

      <section className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("projects.tasks")}
          <Text type="secondary" className={styles.sectionHint}>
            {t("projects.tasksHint")}
          </Text>
        </div>
        <Board
          projectId={project.project_id}
          tasks={tasks}
          canEdit={canEdit}
          onChanged={load}
        />
      </section>

      <Modal
        open={editOpen}
        title={t("projects.update")}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        confirmLoading={saving}
        destroyOnHidden
        onOk={() => editForm.submit()}
        onCancel={closeEdit}
      >
        <Form<ProjectFormValues>
          form={editForm}
          layout="vertical"
          onFinish={(values) => void submitEdit(values)}
        >
          <Form.Item
            name="name"
            label={t("projects.name")}
            rules={[{ required: true, message: t("projects.nameRequired") }]}
          >
            <Input className={styles.field} maxLength={120} />
          </Form.Item>
          <Form.Item name="goal" label={t("projects.goal")}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="status" label={t("projects.status")}>
            <Select<ProjectStatus>
              className={styles.field}
              options={[
                project.status,
                ...STATUS_TRANSITIONS[project.status],
              ].map((status) => ({
                value: status,
                label: t(STATUS_LABEL_KEYS[status]),
              }))}
            />
          </Form.Item>
          <Form.Item name="start_at" label={t("projects.startAt")}>
            <DatePicker
              className={styles.field}
              showTime={{ format: "HH:mm" }}
              format="YYYY-MM-DD HH:mm"
            />
          </Form.Item>
          <Form.Item name="due_at" label={t("projects.dueAt")}>
            <DatePicker
              className={styles.field}
              showTime={{ format: "HH:mm" }}
              format="YYYY-MM-DD HH:mm"
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}

export default ProjectDetailPage;
