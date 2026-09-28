import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ProjectTask } from "../../../api/modules/projects";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import Board from "./Board";

const createTaskMock = vi.fn();
const updateTaskMock = vi.fn();
const timelineMock = vi.fn();
const dispatchTaskMock = vi.fn();
const messageSuccessMock = vi.fn();
const messageErrorMock = vi.fn();

vi.mock("@/utils/antdMessage", () => ({
  message: {
    success: (...args: unknown[]) => messageSuccessMock(...args),
    error: (...args: unknown[]) => messageErrorMock(...args),
    warning: vi.fn(),
  },
}));

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

vi.mock("../../../api/modules/projects", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../../api/modules/projects")
  >();
  return {
    ...actual,
    projectsApi: {
      ...actual.projectsApi,
      createTask: (...args: unknown[]) => createTaskMock(...args),
      updateTask: (...args: unknown[]) => updateTaskMock(...args),
      dispatchTask: (...args: unknown[]) => dispatchTaskMock(...args),
      timeline: (...args: unknown[]) => timelineMock(...args),
    },
  };
});

/** Column order plus the frozen adjacency (PLAN §1.2). */
const STATUS_KEYS = [
  "projects.taskStatusPlanning",
  "projects.taskStatusTodo",
  "projects.taskStatusDoing",
  "projects.taskStatusReview",
  "projects.taskStatusBlocked",
  "projects.taskStatusDone",
  "projects.taskStatusCancelled",
];

const START_AT = 1_750_000_000;

function task(overrides: Partial<ProjectTask> = {}): ProjectTask {
  return {
    task_id: "tsk_1",
    project_id: "prj_1",
    parent_id: null,
    title: "Task one",
    description: "",
    status: "todo",
    assignee_type: null,
    assignee_id: null,
    priority: 1,
    deps: [],
    thread_id: null,
    origin_node_id: null,
    due_at: null,
    start_at: null,
    tags: [],
    custom_fields: [],
    attachments: [],
    sort_order: 0,
    created_by: 1,
    created_at: START_AT,
    updated_at: START_AT,
    ...overrides,
  };
}

function renderBoard(tasks: ProjectTask[] = []) {
  const onChanged = vi.fn();
  render(
    <Board projectId="prj_1" tasks={tasks} canEdit onChanged={onChanged} />,
  );
  return { onChanged };
}

/** Column add buttons render in `COLUMN_STATUSES` order. */
const addButtons = () =>
  screen.getAllByRole("button", { name: "projects.boardAdd" });

describe("Board 7 列与全部列可建", () => {
  beforeEach(() => {
    createTaskMock.mockReset();
    updateTaskMock.mockReset();
    timelineMock.mockReset();
    dispatchTaskMock.mockReset();
    messageSuccessMock.mockReset();
    messageErrorMock.mockReset();
    createTaskMock.mockResolvedValue(task());
    dispatchTaskMock.mockResolvedValue(task());
  });

  it("AC-U-6/S-1: 7 列按序渲染，planning 在列首且不受「显示终态」开关影响", async () => {
    const user = userEvent.setup();
    renderBoard();

    for (const key of STATUS_KEYS) {
      expect(screen.getByText(key)).toBeInTheDocument();
    }
    // planning 在最左（列头 Tag 的 DOM 顺序）。
    const headers = STATUS_KEYS.map((key) => screen.getByText(key));
    for (let i = 1; i < headers.length; i += 1) {
      expect(
        headers[i - 1].compareDocumentPosition(headers[i]) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }

    // 关闭终态开关后 planning 仍可见（S-1：planning 不进 TERMINAL_STATUSES）。
    await user.click(
      screen.getByRole("checkbox", { name: "projects.boardShowTerminal" }),
    );
    expect(screen.getByText("projects.taskStatusPlanning")).toBeInTheDocument();
    expect(
      screen.queryByText("projects.taskStatusDone"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("projects.taskStatusCancelled"),
    ).not.toBeInTheDocument();
  });

  it("AC-U-6/AC-U-7: 7 列每列都有可用的建任务入口（旧限制已作废）", () => {
    renderBoard();

    const buttons = addButtons();
    expect(buttons.length).toBe(7);
    for (const button of buttons) {
      expect(button).toBeEnabled();
    }
  });

  it("AC-U-7/AC-U-9: 内联快速创建保留，且只发一次请求携带目标列状态", async () => {
    const user = userEvent.setup();
    const { onChanged } = renderBoard();

    // 第 3 个入口 = doing 列（列序 planning, todo, doing, …）。
    await user.click(addButtons()[2]);
    const input = screen.getByPlaceholderText("projects.boardAddPlaceholder");
    expect(input).toHaveFocus();
    await user.type(input, "Ship it{Enter}");

    await waitFor(() => expect(createTaskMock).toHaveBeenCalledTimes(1));
    expect(createTaskMock).toHaveBeenCalledWith("prj_1", {
      title: "Ship it",
      status: "doing",
    });
    // 旧的「先建 todo 再 move」两段式已废除。
    expect(updateTaskMock).not.toHaveBeenCalled();
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("内联创建的 Esc 取消不发请求", async () => {
    const user = userEvent.setup();
    renderBoard();

    await user.click(addButtons()[0]);
    const input = screen.getByPlaceholderText("projects.boardAddPlaceholder");
    await user.type(input, "Discarded{Escape}");
    expect(
      screen.queryByPlaceholderText("projects.boardAddPlaceholder"),
    ).not.toBeInTheDocument();
    expect(createTaskMock).not.toHaveBeenCalled();
  });

  it("AC-U-13/AC-U-14/AC-CF-5: 卡片展示标签、自定义字段值与开始日期（服务端时区）", () => {
    renderBoard([
      task({
        tags: [{ tag_id: "tag_1", name: "紧急", color: "#ff0000" }],
        custom_fields: [
          {
            field_id: "fld_1",
            key: "note",
            label: "备注",
            type: "text",
            value: "hello",
          },
          {
            field_id: "fld_2",
            key: "when",
            label: "日期字段",
            type: "date",
            value: START_AT,
          },
        ],
        start_at: START_AT,
      }),
    ]);

    expect(screen.getByText("紧急")).toBeInTheDocument();
    expect(screen.getByText("备注：hello")).toBeInTheDocument();
    expect(
      screen.getByText(`日期字段：${formatServerDateTime(START_AT, "UTC")}`),
    ).toBeInTheDocument();
    // 开始日期用同一个服务端时区格式化助手渲染。
    expect(
      screen.getAllByText(formatServerDateTime(START_AT, "UTC")).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("卡片元数据为空时不渲染附加行", () => {
    renderBoard([task()]);
    const card = screen.getByText("Task one");
    expect(
      within(card.closest("div") as HTMLElement).queryByText("紧急"),
    ).toBeNull();
  });
});

describe("Board 派单（FIND-12 / PLAN §8.1）", () => {
  const dispatchButtons = () =>
    screen.getAllByRole("button", { name: "projects.boardDispatch" });

  beforeEach(() => {
    createTaskMock.mockReset().mockResolvedValue(task());
    dispatchTaskMock.mockReset().mockResolvedValue(task());
    timelineMock.mockReset();
    messageSuccessMock.mockReset();
    messageErrorMock.mockReset();
  });

  it("agent 负责人：按钮可用，点击调用 dispatchTask(projectId, taskId) 并提示成功", async () => {
    const user = userEvent.setup();
    const { onChanged } = renderBoard([
      task({ assignee_type: "agent", assignee_id: "agent-a" }),
    ]);

    const button = dispatchButtons()[0];
    expect(button).toBeEnabled();
    expect(button).toHaveAttribute("title", "projects.boardDispatch");

    await user.click(button);

    await waitFor(() =>
      expect(dispatchTaskMock).toHaveBeenCalledWith("prj_1", "tsk_1"),
    );
    expect(dispatchTaskMock).toHaveBeenCalledTimes(1);
    expect(messageSuccessMock).toHaveBeenCalledTimes(1);
    expect(messageErrorMock).not.toHaveBeenCalled();
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("team 负责人同样可用", async () => {
    const user = userEvent.setup();
    renderBoard([task({ assignee_type: "team", assignee_id: "team-1" })]);

    const button = dispatchButtons()[0];
    expect(button).toBeEnabled();
    await user.click(button);
    await waitFor(() =>
      expect(dispatchTaskMock).toHaveBeenCalledWith("prj_1", "tsk_1"),
    );
  });

  it("user / 空负责人：disabled + title 复用 apiErrors 键，且不调用", async () => {
    const user = userEvent.setup();
    renderBoard([
      task({
        task_id: "tsk_user",
        title: "User task",
        assignee_type: "user",
        assignee_id: "7",
      }),
      task({
        task_id: "tsk_none",
        title: "No assignee",
        assignee_type: null,
        assignee_id: null,
      }),
    ]);

    const buttons = dispatchButtons();
    expect(buttons.length).toBe(2);
    for (const button of buttons) {
      expect(button).toBeDisabled();
      // 复用既有 apiErrors 键作为提示，不新增第二个文案键。
      expect(button).toHaveAttribute(
        "title",
        "apiErrors.PROJECT_TASK_DISPATCH_INVALID",
      );
    }

    await user.click(buttons[0]);
    await user.click(buttons[1]);
    expect(dispatchTaskMock).not.toHaveBeenCalled();
    expect(messageErrorMock).not.toHaveBeenCalled();
  });

  it("失败路径（409）：给出错误提示且不抛异常，仍刷新看板", async () => {
    const user = userEvent.setup();
    dispatchTaskMock.mockRejectedValue(
      new Error(
        'Request failed: 409 Conflict - {"error":{"code":"PROJECT_TASK_DISPATCH_INVALID","message":"该任务的负责人不是可运行的智能体或团队。"}}',
      ),
    );
    const { onChanged } = renderBoard([
      task({ assignee_type: "agent", assignee_id: "agent-a" }),
    ]);

    await user.click(dispatchButtons()[0]);

    await waitFor(() => expect(messageErrorMock).toHaveBeenCalledTimes(1));
    expect(messageSuccessMock).not.toHaveBeenCalled();
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("只读看板不渲染派单入口", () => {
    render(
      <Board
        projectId="prj_1"
        tasks={[task({ assignee_type: "agent" })]}
        canEdit={false}
        onChanged={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "projects.boardDispatch" }),
    ).not.toBeInTheDocument();
  });
});
