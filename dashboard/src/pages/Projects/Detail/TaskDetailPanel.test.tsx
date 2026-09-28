import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

// 只 mock 传输层（真实走 projectsApi / projectMetadataApi 的路径与请求体）。
vi.mock("../../../api/request", () => ({
  request: vi.fn(),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

import { request, requestBlob } from "../../../api/request";
import type { ProjectTask } from "../../../api/modules/projects";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { STATUS_LABEL_KEYS } from "../utils/taskStatus";
import TaskDetailPanel, { hasTaskDetailParam } from "./TaskDetailPanel";

const mockedRequest = vi.mocked(request);
const mockedRequestBlob = vi.mocked(requestBlob);

const CREATED_AT = 1_750_000_000;
const UPDATED_AT = 1_750_900_000;
const DUE_AT = 1_750_600_000;

function task(overrides: Partial<ProjectTask> = {}): ProjectTask {
  return {
    task_id: "tsk_1",
    project_id: "prj_1",
    parent_id: null,
    title: "Ship it",
    description: "Full description",
    status: "doing",
    assignee_type: "agent",
    assignee_id: "agent01",
    priority: 3,
    deps: [],
    thread_id: null,
    origin_node_id: null,
    due_at: DUE_AT,
    start_at: CREATED_AT,
    tags: [{ tag_id: "tag_1", name: "urgent", color: "#ff0000" }],
    custom_fields: [
      {
        field_id: "fld_1",
        key: "env",
        label: "Environment",
        type: "text",
        value: "prod",
      },
    ],
    attachments: [
      {
        artifact_id: "art_1",
        name: "spec.pdf",
        size: 2048,
        mime: "application/pdf",
        created_at: CREATED_AT,
        uploader: "admin",
        task_id: "tsk_1",
      },
    ],
    sort_order: 0,
    created_by: 1,
    created_at: CREATED_AT,
    updated_at: UPDATED_AT,
    ...overrides,
  };
}

/** timeline 路由（既有端点 + `task_id`）。 */
function mockTimeline(events: unknown[]) {
  const previous = mockedRequest.getMockImplementation();
  mockedRequest.mockImplementation(async (path: string, init?: RequestInit) => {
    if (String(path).includes("/timeline")) return events as never;
    return previous ? previous(path, init) : (task() as never);
  });
}

function renderPanel(
  overrides: Partial<{
    task: ProjectTask | undefined;
    loading: boolean;
    canEdit: boolean;
  }> = {},
) {
  const onBack = vi.fn();
  const onChanged = vi.fn(async () => {});
  const current = "task" in overrides ? overrides.task : task();
  const view = render(
    <TaskDetailPanel
      projectId="prj_1"
      task={current}
      loading={overrides.loading ?? false}
      canEdit={overrides.canEdit ?? true}
      tasks={current ? [current] : []}
      onBack={onBack}
      onChanged={onChanged}
    />,
  );
  return { onBack, onChanged, view };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedRequest.mockImplementation(async (path: string) => {
    if (path === "/settings/timezone") return { timezone: "UTC" };
    throw new Error(`unexpected request: ${path}`);
  });
});

describe("TaskDetailPanel — 逐字段渲染（AC-G4-2）", () => {
  it("渲染 10 个字段区（描述/状态/优先级/负责人/父任务/依赖/标签/自定义字段/附件/过程）", async () => {
    renderPanel();

    expect(screen.getByTestId("task-detail-panel")).toBeInTheDocument();
    expect(screen.getByText("Ship it")).toBeInTheDocument();

    // 逐字段 testid（PLAN §4.4 逐字）。
    for (const field of [
      "description",
      "status",
      "priority",
      "assignee",
      "parent",
      "deps",
      "tags",
      "custom-fields",
      "attachments",
      "timeline",
    ]) {
      // 「过程」区在批次八由容器 testid 承载（`task-detail-<field>` 逐字段口径保留）。
      const testId =
        field === "timeline" ? "task-detail-history" : `task-detail-${field}`;
      expect(screen.getByTestId(testId)).toBeInTheDocument();
    }

    expect(screen.getByTestId("task-detail-description")).toHaveTextContent(
      "Full description",
    );
    expect(screen.getByTestId("task-detail-status")).toHaveTextContent(
      STATUS_LABEL_KEYS.doing,
    );
    expect(screen.getByTestId("task-detail-priority")).toHaveTextContent("3");
    expect(screen.getByTestId("task-detail-assignee")).toHaveTextContent(
      "agent:agent01",
    );
    expect(screen.getByTestId("task-detail-tags")).toHaveTextContent("urgent");
    expect(screen.getByTestId("task-detail-custom-fields")).toHaveTextContent(
      "Environment",
    );
    expect(screen.getByTestId("task-detail-custom-fields")).toHaveTextContent(
      "prod",
    );
    // 时间用服务端时区格式化（禁裸 toLocaleString）。
    expect(screen.getByTestId("task-detail-attachments")).toHaveTextContent(
      "spec.pdf",
    );
  });

  it("空的可选字段（父任务/依赖/标签/自定义字段/附件）显示占位而非崩溃", async () => {
    renderPanel({
      task: task({
        parent_id: null,
        deps: [],
        tags: [],
        custom_fields: [],
        attachments: [],
        description: "",
      }),
    });

    expect(screen.getByTestId("task-detail-parent")).toBeInTheDocument();
    expect(screen.getByTestId("task-detail-deps")).toBeInTheDocument();
    expect(screen.getByTestId("task-detail-tags")).toBeInTheDocument();
    expect(screen.getByTestId("task-detail-custom-fields")).toBeInTheDocument();
    expect(screen.getByTestId("task-detail-attachments")).toBeInTheDocument();
  });

  it("父任务显示其标题（来自同一份列表数据，不新增读取环）", async () => {
    const parent = task({ task_id: "tsk_p", title: "Parent task" });
    const child = task({
      task_id: "tsk_c",
      title: "Child",
      parent_id: "tsk_p",
    });
    const onBack = vi.fn();
    render(
      <TaskDetailPanel
        projectId="prj_1"
        task={child}
        canEdit={false}
        tasks={[parent, child]}
        onBack={onBack}
        onChanged={vi.fn()}
      />,
    );

    expect(screen.getByTestId("task-detail-parent")).toHaveTextContent(
      "Parent task",
    );
  });
});

describe("TaskDetailPanel — 完整状态流转史（批次八 AC-A-5 / A-6 / A-7）", () => {
  /** 12 条事件（AC-A-5：**不得截断** ⇒ 节点数 == 12）。 */
  const EVENTS = Array.from({ length: 12 }, (_, index) => ({
    actor: `user:${index + 1}`,
    action: "status_change",
    task_id: "tsk_1",
    payload: { from: `s${index}`, to: `s${index + 1}` },
    at: 1_750_000_000 + index * 60,
  }));

  it("12 条事件 → 渲染 12 个 timeline-node（**全量、不 slice**）", async () => {
    mockTimeline(EVENTS);
    renderPanel();

    await waitFor(() =>
      expect(screen.getAllByTestId("timeline-node")).toHaveLength(12),
    );
    // 走既有端点 + `task_id` 过滤（不新增端点）。
    expect(
      mockedRequest.mock.calls.some(([p]) =>
        String(p).includes("/projects/prj_1/timeline?task_id=tsk_1"),
      ),
    ).toBe(true);
  });

  it("AC-A-6：每条含 时间（服务器时区）/ 操作人 / 前后状态（payload.from → to）", async () => {
    mockTimeline(EVENTS);
    renderPanel();

    const nodes = await screen.findAllByTestId("timeline-node");
    const first = nodes[0];
    expect(first).toHaveTextContent("user:1");
    expect(first).toHaveTextContent("s0 → s1");
    expect(first).toHaveTextContent(formatServerDateTime(1_750_000_000, "UTC"));
  });

  it("★ 操作人显示【名字】而非裸标识；actor_name 缺失 ⇒ 回退 actor（不得空白）", async () => {
    mockTimeline([
      {
        actor: "user:1",
        actor_name: "李四",
        action: "status_change",
        task_id: "tsk_1",
        payload: { from: "a", to: "b" },
        at: 1_750_000_000,
      },
      {
        actor: "agent:agt_9",
        actor_name: null,
        action: "status_change",
        task_id: "tsk_1",
        payload: { from: "b", to: "c" },
        at: 1_750_000_060,
      },
    ]);
    renderPanel();

    const nodes = await screen.findAllByTestId("timeline-node");
    const named = within(nodes[0]).getByTestId("timeline-actor");
    expect(named).toHaveTextContent("李四");
    expect(named).not.toHaveTextContent("user:1"); // ★ 不显示稳定标识
    const bare = within(nodes[1]).getByTestId("timeline-actor");
    expect(bare).toHaveTextContent("agent:agt_9"); // 回退（不得空白）
  });

  it("AC-A-7：无流转 → 空态（不报错、不空白）", async () => {
    mockTimeline([]);
    renderPanel();

    expect(
      await screen.findByTestId("task-detail-timeline-empty"),
    ).toHaveTextContent("projects.taskDetailTimelineEmpty");
    expect(screen.queryAllByTestId("timeline-node")).toHaveLength(0);
  });

  it("★ 只读：流转区没有任何编辑控件（无 button / input）", async () => {
    mockTimeline(EVENTS);
    renderPanel();
    const list = await screen.findByTestId("task-detail-timeline");
    expect(
      list.querySelectorAll("button, input, textarea, select"),
    ).toHaveLength(0);
  });
});

describe("TaskDetailPanel — 编辑复用 TaskCreateModal 差异提交（AC-G4-3 / AC-G4-6）", () => {
  it("点「编辑」打开弹窗；只改标题 → PATCH 体只含 title，且 onChanged 被调用（重读）", async () => {
    mockedRequest.mockImplementation(
      async (path: string, init?: RequestInit) => {
        if (path === "/settings/timezone") return { timezone: "UTC" };
        if (path === "/projects/prj_1/members") return [];
        if (path === "/projects/prj_1/tasks/tsk_1") {
          return task({ title: "Renamed" });
        }
        throw new Error(`unexpected request: ${init?.method ?? "GET"} ${path}`);
      },
    );

    const current = task();
    const { onChanged } = renderPanel({ task: current });

    await userEvent.click(screen.getByTestId("task-detail-edit"));
    const dialog = await screen.findByRole("dialog");
    const titleInput = within(dialog).getByDisplayValue("Ship it");
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, "Renamed");
    await userEvent.click(
      // 提交按钮的可访问名带快捷键后缀（"…⌘↵"）→ 用前缀正则。
      within(dialog).getByRole("button", { name: /projects\.editTaskSubmit/ }),
    );

    await waitFor(() => {
      expect(onChanged).toHaveBeenCalled();
    });
    const patch = mockedRequest.mock.calls.find(
      ([path, init]) =>
        path === "/projects/prj_1/tasks/tsk_1" &&
        (init as RequestInit | undefined)?.method === "PATCH",
    );
    expect(patch).toBeTruthy();
    // ★ 差异提交：只有改动的字段进请求体。
    expect(JSON.parse(String((patch?.[1] as RequestInit).body))).toEqual({
      title: "Renamed",
    });
  });

  it("canEdit=false（viewer）→ 没有编辑入口", async () => {
    renderPanel({ canEdit: false });
    expect(screen.queryByTestId("task-detail-edit")).toBeNull();
  });

  it("返回列表：点返回调用 onBack（移除 ?task=，列表由 owner 重读）", async () => {
    const { onBack } = renderPanel();
    await userEvent.click(screen.getByTestId("task-detail-back"));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});

describe("TaskDetailPanel — 附件只读 + 下载（AC-G4-5）", () => {
  it("列出附件并可下载（走既有下载端点），且**没有**上传/删除控件", async () => {
    mockedRequestBlob.mockResolvedValue(new Blob(["x"]));
    renderPanel();

    const attachments = screen.getByTestId("task-detail-attachments");
    expect(
      within(attachments).getByTestId("task-detail-attachment-art_1"),
    ).toHaveTextContent("spec.pdf");

    await userEvent.click(
      within(attachments).getByTestId("task-detail-download-art_1"),
    );
    await waitFor(() => {
      expect(mockedRequestBlob).toHaveBeenCalledWith(
        "/projects/prj_1/attachments/art_1/download",
      );
    });

    // 本轮不做上传 / 删除：文件选择器与删除按钮都不存在。
    expect(attachments.querySelector('input[type="file"]')).toBeNull();
    expect(
      within(attachments).queryByRole("button", { name: /delete|删除/i }),
    ).toBeNull();
  });

  it("无附件 → 显示空态文案（不崩溃）", async () => {
    renderPanel({ task: task({ attachments: [] }) });
    expect(screen.getByTestId("task-detail-attachments")).toHaveTextContent(
      "projects.attachmentsEmpty",
    );
  });
});

describe("TaskDetailPanel — 缺失 / 优雅降级（AC-G4-1 进入方式）", () => {
  it("★ ?task=<id> 不存在 → 显示 taskDetailNotFound，不白屏", async () => {
    renderPanel({ task: undefined });
    expect(screen.getByTestId("task-detail-not-found")).toHaveTextContent(
      "projects.taskDetailNotFound",
    );
    // 不白屏：面板骨架仍在（可返回列表）。
    expect(screen.getByTestId("task-detail-panel")).toBeInTheDocument();
    expect(screen.getByTestId("task-detail-back")).toBeInTheDocument();
  });

  it("深链重取中（loading=true）→ 不误报「不存在」", async () => {
    renderPanel({ task: undefined, loading: true });
    expect(screen.queryByTestId("task-detail-not-found")).toBeNull();
  });

  it("★ 缺 tab 参数：hasTaskDetailParam 以 task 为准（有 task 即进详情）", () => {
    expect(hasTaskDetailParam(new URLSearchParams("task=tsk_1"))).toBe(true);
    expect(
      hasTaskDetailParam(new URLSearchParams("tab=tasks&task=tsk_1")),
    ).toBe(true);
    expect(hasTaskDetailParam(new URLSearchParams("tab=tasks"))).toBe(false);
    expect(hasTaskDetailParam(new URLSearchParams("task="))).toBe(false);
    expect(hasTaskDetailParam(new URLSearchParams(""))).toBe(false);
  });
});
