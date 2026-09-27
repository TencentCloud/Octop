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
  Tag,
  Tooltip,
  Typography,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import {
  Activity,
  BookOpen,
  LayoutGrid,
  List,
  Pencil,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  projectsApi,
  type ProjectMember,
  type ProjectOut,
  type ProjectStatus,
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
import AssetsTab from "./AssetsTab";
import CustomFieldsPanel from "./CustomFieldsPanel";
import DynamicTab from "./DynamicTab";
import RightRail from "./RightRail";
import TaskListView from "./TaskListView";
import styles from "./index.module.less";
import TagsManager from "./TagsManager";
import TabBar, { type TabBarItem } from "../../../components/TabLabel/TabBar";

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

interface ProjectFormValues {
  name: string;
  goal?: string;
  status: ProjectStatus;
  start_at?: Dayjs | null;
  due_at?: Dayjs | null;
}

/** 4 Tab（PLAN §4.1）：动态占位 / 计划看板 / 任务列表 / 资产。 */
type DetailTabKey = "dynamic" | "plan" | "tasks" | "assets";

const DETAIL_TABS: TabBarItem<DetailTabKey>[] = [
  { key: "dynamic", labelKey: "projects.tabDynamic", icon: Activity },
  { key: "plan", labelKey: "projects.tabPlan", icon: LayoutGrid },
  { key: "tasks", labelKey: "projects.tabTasks", icon: List },
  { key: "assets", labelKey: "projects.tabAssets", icon: BookOpen },
];

/** S5：缺省与非法值（含空串）一律回落 `plan`，且不把非法值写回 URL。 */
function parseTab(raw: string | null): DetailTabKey {
  const found = DETAIL_TABS.find((tab) => tab.key === raw);
  return found ? found.key : "plan";
}

function ProjectDetailPage() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const timeZone = useServerTimezone();
  const currentUser = useCurrentUser();
  const [editForm] = Form.useForm<ProjectFormValues>();

  // Tab 表达 = 查询参数 `?tab=`（PLAN §4）：不新增顶层路由，刷新保留。
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = parseTab(searchParams.get("tab"));
  const selectTab = useCallback(
    (next: DetailTabKey) => {
      const updated = new URLSearchParams(searchParams);
      updated.set("tab", next);
      // `replace`：切 Tab 不堆历史（与 Settings/Models 的写法一致）。
      setSearchParams(updated, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const [project, setProject] = useState<ProjectOut | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [tasks, setTasks] = useState<ProjectTask[]>([]);
  /** 任务增删改后 +1 → TaskListView 重新取数（PLAN §9 的 refreshKey）。 */
  const [tasksRefreshKey, setTasksRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const loadedOnceRef = useRef(false);

  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);

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
      setTasksRefreshKey((value) => value + 1);
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
  /** PLAN §6：`PROJECT_MANAGE_CONFIG` = owner + admin（member/viewer 看不到右栏配置面板）。 */
  const canManageConfig = canManageMembers;

  /**
   * `TaskListView` 的行点击入口。**任务详情页属第三批范围**（PLAN §0「本轮不
   * 做」清单）→ 这里只保留入口契约，不自造详情视图；第三批接线时替换本回调。
   */
  const openTask = useCallback((_taskId: string) => undefined, []);

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

      {/* 布局（PLAN §4）：主区（TabBar + 当前 Tab 内容）在前，右栏在后 ——
          S6 要求窄屏堆叠时 DOM 顺序即「主区 → 右栏」，不得用 CSS order 提前。 */}
      <div className={styles.detailLayout}>
        <div className={styles.mainColumn}>
          <TabBar
            tabs={DETAIL_TABS}
            activeKey={activeTab}
            onChange={selectTab}
          />

          {activeTab === "dynamic" ? (
            /* S9：占位只用 dynamicPlaceholder + dynamicComingSoon，零请求、不加图标。 */
            <DynamicTab />
          ) : null}

          {activeTab === "plan" ? (
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
          ) : null}

          {activeTab === "tasks" ? (
            <>
              <TaskListView
                projectId={project.project_id}
                onOpenTask={openTask}
                refreshKey={tasksRefreshKey}
              />
              {/* PLAN §4.2：标签定义与自定义字段定义两个面板归 `tasks` Tab
                  （防死 schema 的两条读环断言依赖它们默认挂载）。 */}
              <TagsManager projectId={project.project_id} canEdit={canEdit} />
              <CustomFieldsPanel
                projectId={project.project_id}
                canEdit={canEdit}
              />
            </>
          ) : null}

          {activeTab === "assets" ? <AssetsTab kbId={project.kb_id} /> : null}
        </div>

        <RightRail
          projectId={project.project_id}
          canManageConfig={canManageConfig}
          canManageMembers={canManageMembers}
        />
      </div>

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
