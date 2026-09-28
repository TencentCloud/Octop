import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Only the transport is mocked, so the view really goes through
// ``projectsApi.listTasks`` (the frozen data face) and the shared status module.
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

import { request } from "../../../api/request";
import type {
  ProjectTask,
  ProjectTaskStatus,
} from "../../../api/modules/projects";
import zh from "../../../locales/zh.json";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import {
  COLUMN_STATUSES,
  STATUS_COLORS,
  STATUS_LABEL_KEYS,
} from "../utils/taskStatus";
import TaskListView, { TASK_LIST_COLUMN_KEYS } from "./TaskListView";

const mockedRequest = vi.mocked(request);

const START_AT = 1_750_000_000;
const DUE_AT = 1_750_600_000;
const UPDATED_AT = 1_750_900_000;

/** ★ 列面期望值 = **字面量**（不从被测模块推导，避免自证循环）。 */
const COLUMN_KEYS = [
  "projects.taskListColumnStatus",
  "projects.taskListColumnTitle",
  "projects.taskListColumnAssignee",
  "projects.taskListColumnPriority",
  "projects.taskListColumnStartAt",
  "projects.taskListColumnDueAt",
  "projects.taskListColumnTags",
  "projects.taskListColumnUpdatedAt",
];

/** 独立取自 i18n 资源侧的 zh 文案（字面量，用于第二条机判的交叉锚）。 */
const COLUMN_ZH = [
  "状态",
  "标题",
  "负责人",
  "优先级",
  "开始",
  "截止",
  "标签",
  "更新时间",
];

/**
 * 列面断言辅助 —— 机判 ①② 与 ③ 用**同一套**断言，因此 ③ 的判别性对照
 * （9 列 fixture 必失败）直接证明 ①② 有判别力（不是自证循环）。
 */
function assertColumnFace(headers: string[]) {
  expect(headers).toHaveLength(8);
  expect(headers).toEqual(COLUMN_KEYS);
}

/**
 * 卡片判据辅助（G1 AC-G1-1）——「7 张卡片且顺序 = 词表序」。
 * 判别性对照用**同一套**辅助函数，故 ③ 的对照直接证明本判据有判别力。
 */
function assertSevenCards(ids: string[]) {
  expect(ids).toHaveLength(7);
  expect(ids).toEqual(
    COLUMN_STATUSES.map((status) => `task-section-card-${status}`),
  );
}

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

function renderList(
  refreshKey?: number,
  onEditTask?: (taskId: string) => void,
) {
  const onOpenTask = vi.fn();
  const view = render(
    <TaskListView
      projectId="prj_1"
      onOpenTask={onOpenTask}
      refreshKey={refreshKey}
      onEditTask={onEditTask}
    />,
  );
  return { onOpenTask, view };
}

function mockTasks(rows: ProjectTask[]) {
  mockedRequest.mockImplementation(async (path: string) => {
    if (path === "/settings/timezone") return { timezone: "UTC" };
    if (path === "/projects/prj_1/tasks") return rows;
    throw new Error(`unexpected request: ${path}`);
  });
}

/**
 * 当前渲染出的表头文本。
 *
 * ⚠️ 与 PLAN §5.3 ① 的**字面**口径（`getAllByRole("columnheader", {hidden:true})`
 * == 8）的偏差与原因（已回报 Lead）：antd 在 `scroll.x` 下会往 tbody 里塞一行
 * `ant-table-measure-row`（8 个 `<th class="ant-table-measure-cell">`，内容就是同样
 * 的 8 个列名）→ 字面口径恒为 16，**改造前的旧代码也是 16**（PLAN 机判缺陷）。
 * 这里采用 PLAN **同一句给出的替代口径** `table.querySelectorAll("thead th")`，
 * 它同样包含隐藏元素（`querySelectorAll` 不过滤 `aria-hidden`/`hidden`），
 * 并对「第 9 列」仍然敏感（③ 的判别性对照用同一套辅助函数）。
 */
function tableHeadCells(): HTMLElement[] {
  return Array.from(
    screen.getByRole("table").querySelectorAll<HTMLElement>("thead th"),
  );
}

function renderedHeaders(): string[] {
  return tableHeadCells().map((cell) => cell.textContent ?? "");
}

/** 区块容器 testid，按 DOM 顺序。 */
function zoneIds(): string[] {
  return screen
    .getAllByTestId(
      /^task-section-(planning|todo|doing|review|blocked|done|cancelled)$/,
    )
    .map((node) => node.getAttribute("data-testid") ?? "");
}

/** 某个区块内的任务行标题（DOM 顺序 = 区内顺序）。 */
function zoneRowTitles(status: ProjectTaskStatus): string[] {
  return screen
    .getAllByTestId(/^task-row-title-/)
    .filter(
      (node) =>
        node.closest("[data-section]")?.getAttribute("data-section") === status,
    )
    .map((node) => node.textContent ?? "");
}

/** 全部任务行标题，按 DOM 顺序。 */
function rowTitles(): string[] {
  return screen
    .getAllByTestId(/^task-row-title-/)
    .map((node) => node.textContent ?? "");
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTasks([]);
});

describe("TaskListView", () => {
  it("renders the eight frozen columns from the shared status vocabulary", async () => {
    mockTasks([
      task({
        task_id: "tsk_1",
        title: "Ship it",
        status: "doing",
        assignee_type: "agent",
        assignee_id: "agent01",
        priority: 3,
        start_at: START_AT,
        due_at: DUE_AT,
        updated_at: UPDATED_AT,
        tags: [{ tag_id: "tag_1", name: "urgent", color: "#ff0000" }],
      }),
    ]);

    renderList();

    await waitFor(() => {
      expect(screen.getByText("Ship it")).toBeInTheDocument();
    });

    // Status cell: shared label key + shared antd colour (区块标题也用同一文案，
    // 因此按 class 挑出状态 Tag 本身)。
    const statusTag = screen
      .getAllByText(STATUS_LABEL_KEYS.doing)
      .find((node) =>
        node.classList.contains(`ant-tag-${STATUS_COLORS.doing}`),
      );
    expect(statusTag).toBeTruthy();

    // Assignee is rendered as `assignee_type:assignee_id` (PLAN §9).
    expect(screen.getByText("agent:agent01")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("urgent")).toBeInTheDocument();

    // Dates: formatServerDateTime(epochSec, serverTimeZone), never toLocaleString.
    expect(
      screen.getByText(formatServerDateTime(START_AT, "UTC")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(formatServerDateTime(DUE_AT, "UTC")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(formatServerDateTime(UPDATED_AT, "UTC")),
    ).toBeInTheDocument();
  });

  it("G4 推翻 S8(b) 的「纯文本」一半：标题可点；编辑仍是独立图标按钮（S8(b) 保留项）", async () => {
    mockTasks([task({ task_id: "tsk_42", title: "Open me" })]);
    const onEditTask = vi.fn();

    const { view } = renderList(undefined, onEditTask);
    const title = await screen.findByTestId("task-row-title-tsk_42");

    // PLAN §4.1：标题 = 导航入口（可点元素）。★ 本条取代批次三 S8(b) 的「非 button」断言。
    expect(title.tagName).toBe("BUTTON");
    // 编辑入口与标题是**两个不同元素**（不得把标题变成编辑入口）。
    const editNode = screen.getByTestId("task-row-edit-tsk_42");
    expect(editNode).not.toBe(title);
    expect(title.contains(editNode)).toBe(false);

    // 编辑入口：常显图标按钮 + 非空 aria-label + 点击回调。
    const edit = screen.getByTestId("task-row-edit-tsk_42");
    expect(edit).toHaveAttribute("aria-label", "projects.editTaskTitle");
    fireEvent.click(edit);
    expect(onEditTask).toHaveBeenCalledWith("tsk_42");

    // 未传 onEditTask → 无编辑按钮。
    view.unmount();
    mockTasks([task({ task_id: "tsk_43", title: "No edit" })]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_43");
    expect(screen.queryByTestId("task-row-edit-tsk_43")).toBeNull();
  });

  it("sorts by (sort_order, task_id) so ties are deterministic (S7)", async () => {
    // Deliberately unsorted, and two rows share sort_order 5.
    mockTasks([
      task({ task_id: "tsk_b", title: "B", status: "todo", sort_order: 5 }),
      task({ task_id: "tsk_c", title: "C", status: "todo", sort_order: 1 }),
      task({ task_id: "tsk_a", title: "A", status: "todo", sort_order: 5 }),
    ]);

    renderList();

    await waitFor(() => {
      expect(zoneRowTitles("todo")).toEqual(["C", "A", "B"]);
    });
  });

  it("filters by status, with every status selected by default", async () => {
    mockTasks([
      task({ task_id: "tsk_1", title: "Todo task", status: "todo" }),
      task({
        task_id: "tsk_2",
        title: "Doing task",
        status: "doing",
        sort_order: 1,
      }),
    ]);

    renderList();
    await waitFor(() => {
      expect(rowTitles()).toEqual(["Todo task", "Doing task"]);
    });

    // Deselect `todo` in the status filter.
    fireEvent.mouseDown(screen.getByRole("combobox"));
    const dropdown = document.querySelector(
      ".ant-select-dropdown",
    ) as HTMLElement;
    expect(dropdown).toBeTruthy();
    fireEvent.click(
      Array.from(dropdown.querySelectorAll(".ant-select-item-option")).find(
        (option) => option.textContent === STATUS_LABEL_KEYS.todo,
      ) as HTMLElement,
    );

    await waitFor(() => {
      expect(rowTitles()).toEqual(["Doing task"]);
    });
  });

  it("filters by keyword across title and description", async () => {
    mockTasks([
      task({ task_id: "tsk_1", title: "Alpha", description: "first" }),
      task({
        task_id: "tsk_2",
        title: "Beta",
        description: "mentions gamma",
        sort_order: 1,
      }),
    ]);

    renderList();
    await waitFor(() => {
      expect(rowTitles()).toEqual(["Alpha", "Beta"]);
    });

    const keyword = screen.getByPlaceholderText(
      "projects.taskListFilterKeyword",
    );
    // Description match.
    fireEvent.change(keyword, { target: { value: "gamma" } });
    await waitFor(() => {
      expect(rowTitles()).toEqual(["Beta"]);
    });

    // Title match, case-insensitively.
    fireEvent.change(keyword, { target: { value: "ALPHA" } });
    await waitFor(() => {
      expect(rowTitles()).toEqual(["Alpha"]);
    });
  });

  it("re-reads when the parent bumps refreshKey", async () => {
    mockTasks([task({ task_id: "tsk_1", title: "First" })]);

    const { view } = renderList(0);
    await screen.findByTestId("task-row-title-tsk_1");
    const callsBefore = mockedRequest.mock.calls.filter(
      ([path]) => path === "/projects/prj_1/tasks",
    ).length;

    view.rerender(
      <TaskListView projectId="prj_1" onOpenTask={vi.fn()} refreshKey={1} />,
    );

    await waitFor(() => {
      expect(
        mockedRequest.mock.calls.filter(
          ([path]) => path === "/projects/prj_1/tasks",
        ).length,
      ).toBe(callsBefore + 1);
    });
  });
});

describe("F1 按状态分区（PLAN §1）", () => {
  it("AC-F1-1: 7 个区块恒显，顺序 == COLUMN_STATUSES，标题/计数各带 testid", async () => {
    mockTasks([
      task({ task_id: "tsk_1", title: "Todo task", status: "todo" }),
      task({
        task_id: "tsk_2",
        title: "Todo two",
        status: "todo",
        sort_order: 1,
      }),
      task({
        task_id: "tsk_3",
        title: "Doing task",
        status: "doing",
        sort_order: 2,
      }),
    ]);

    renderList();
    await waitFor(() => {
      expect(zoneIds()).toHaveLength(7);
    });

    // 区块顺序 = 词表序。
    expect(zoneIds()).toEqual(
      COLUMN_STATUSES.map((status) => `task-section-${status}`),
    );

    // 标题 = 共享词表的本地化文案；计数 = 该区行数。
    for (const status of COLUMN_STATUSES) {
      expect(
        screen.getByTestId(`task-section-title-${status}`),
      ).toHaveTextContent(STATUS_LABEL_KEYS[status]);
      const expected = status === "todo" ? 2 : status === "doing" ? 1 : 0;
      expect(
        screen.getByTestId(`task-section-count-${status}`),
      ).toHaveTextContent(String(expected));
      expect(zoneRowTitles(status)).toHaveLength(expected);
    }
  });

  it("AC-F1-2: 空区显示 taskListEmpty（不隐藏区块）；筛选只减少区内行", async () => {
    mockTasks([
      task({ task_id: "tsk_1", title: "Alpha", status: "todo" }),
      task({ task_id: "tsk_2", title: "Beta", status: "doing", sort_order: 1 }),
    ]);

    renderList();
    await waitFor(() => expect(zoneIds()).toHaveLength(7));

    // 全空态：除 todo/doing 外的 5 个区各一行空态。
    const emptyZones = COLUMN_STATUSES.filter(
      (status) => status !== "todo" && status !== "doing",
    );
    for (const status of emptyZones) {
      expect(
        screen.getByTestId(`task-section-empty-${status}`),
      ).toHaveTextContent("projects.taskListEmpty");
    }

    // 关键字筛掉 todo → 该区变空区，但**仍是 7 个区块**。
    fireEvent.change(
      screen.getByPlaceholderText("projects.taskListFilterKeyword"),
      { target: { value: "beta" } },
    );
    await waitFor(() => {
      expect(rowTitles()).toEqual(["Beta"]);
    });
    expect(zoneIds()).toHaveLength(7);
    expect(screen.getByTestId("task-section-empty-todo")).toBeInTheDocument();
    expect(screen.getByTestId("task-section-count-todo")).toHaveTextContent(
      "0",
    );
  });

  it("AC-F1-2/S5G5: 状态多选取消某状态后仍 7 区（只是该区变空）", async () => {
    mockTasks([
      task({ task_id: "tsk_1", title: "Alpha", status: "todo" }),
      task({ task_id: "tsk_2", title: "Beta", status: "doing", sort_order: 1 }),
    ]);

    renderList();
    await waitFor(() => expect(rowTitles()).toEqual(["Alpha", "Beta"]));

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const dropdown = document.querySelector(
      ".ant-select-dropdown",
    ) as HTMLElement;
    fireEvent.click(
      Array.from(dropdown.querySelectorAll(".ant-select-item-option")).find(
        (option) => option.textContent === STATUS_LABEL_KEYS.doing,
      ) as HTMLElement,
    );

    await waitFor(() => expect(rowTitles()).toEqual(["Alpha"]));
    expect(zoneIds()).toHaveLength(7);
    expect(screen.getByTestId("task-section-empty-doing")).toHaveTextContent(
      "projects.taskListEmpty",
    );
  });

  it("AC-F1-3: 数据源不变（单次 listTasks，无分页/新端点）", async () => {
    mockTasks([task({ task_id: "tsk_1", title: "Alpha" })]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_1");

    const paths = mockedRequest.mock.calls.map(([path]) => path);
    // 恰一次 listTasks（无分页、无新端点）。
    expect(
      paths.filter((path) => path === "/projects/prj_1/tasks"),
    ).toHaveLength(1);
    expect(
      paths.filter(
        (path) =>
          path !== "/projects/prj_1/tasks" && path !== "/settings/timezone",
      ),
    ).toEqual([]);
  });

  it("AC-F1-5: 传 onEditTask 时每行都有编辑按钮；未传时没有", async () => {
    mockTasks([
      task({ task_id: "tsk_1", title: "Alpha" }),
      task({ task_id: "tsk_2", title: "Beta", sort_order: 1 }),
    ]);

    const onEditTask = vi.fn();
    const { view } = renderList(undefined, onEditTask);
    await waitFor(() => {
      expect(screen.getAllByTestId(/^task-row-edit-/)).toHaveLength(2);
    });

    for (const button of screen.getAllByTestId(/^task-row-edit-/)) {
      expect(button.getAttribute("aria-label")).toBeTruthy();
    }
    fireEvent.click(screen.getByTestId("task-row-edit-tsk_2"));
    expect(onEditTask).toHaveBeenCalledWith("tsk_2");

    view.unmount();
    mockTasks([task({ task_id: "tsk_1", title: "Alpha" })]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_1");
    expect(screen.queryAllByTestId(/^task-row-edit-/)).toHaveLength(0);
  });
});

describe("列面冻结 8 列（PLAN §5.3 机判 ①②③）", () => {
  it("① 单个 table 内 8 个 columnheader（hidden:true），并与导出列面对照", async () => {
    mockTasks([task({ task_id: "tsk_1", title: "Alpha", status: "doing" })]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_1");

    const table = screen.getByRole("table");
    // (a) 真实列面 = thead 的 8 个 th（`querySelectorAll` 含隐藏列 → 防第 9 列漏判）。
    expect(table.querySelectorAll("thead th")).toHaveLength(8);
    // (b) antd 的测宽行同为 8 列（防第 9 列只出现在测宽行里）。
    const measureCells = table.querySelectorAll(".ant-table-measure-row th");
    expect(measureCells).toHaveLength(8);
    // (c) `hidden:true` 口径下的 columnheader 只允许来自 thead + 测宽行，别无其它
    //     （这才是「有没有第 9 列」的真正判据）。
    const roleHeaders = within(table).getAllByRole("columnheader", {
      hidden: true,
    });
    expect(roleHeaders).toHaveLength(
      tableHeadCells().length + measureCells.length,
    );
    expect(
      roleHeaders.filter(
        (cell) =>
          !cell.closest("thead") && !cell.closest(".ant-table-measure-row"),
      ),
    ).toHaveLength(0);
    // 与导出的列面长度对照。
    expect(TASK_LIST_COLUMN_KEYS).toHaveLength(8);
    expect(renderedHeaders()).toHaveLength(TASK_LIST_COLUMN_KEYS.length);
  });

  it("② 表头文本【有序数组】等于 8 个字面量（断顺序，不只断数量）", async () => {
    mockTasks([task({ task_id: "tsk_1", title: "Alpha", status: "doing" })]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_1");

    assertColumnFace(renderedHeaders());
    // 独立锚：这 8 个键在 zh 资源里映射到 8 个互不相同的文案。
    const copy = zh.projects as Record<string, string>;
    expect(
      COLUMN_KEYS.map((key) => copy[key.replace(/^projects\./, "")]),
    ).toEqual(COLUMN_ZH);
    expect(new Set(COLUMN_ZH).size).toBe(8);
  });

  it("③ 判别性对照（可复跑）：9 列 fixture 必须让同一断言辅助函数失败", async () => {
    // 正例：真实 DOM 走同一套辅助函数 → 通过。
    mockTasks([task({ task_id: "tsk_1", title: "Alpha", status: "doing" })]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_1");
    expect(() => assertColumnFace(renderedHeaders())).not.toThrow();

    // 反例：多一列（第 9 列「操作」）→ 必失败。
    const nineColumns = [...COLUMN_KEYS, "projects.taskListColumnActions"];
    expect(() => assertColumnFace(nineColumns)).toThrow();
    // 少一列 / 顺序错 → 也必失败（防止「只断数量」的退化）。
    expect(() => assertColumnFace(COLUMN_KEYS.slice(0, 7))).toThrow();
    expect(() => assertColumnFace([...COLUMN_KEYS].reverse())).toThrow();
  });
});

describe("status mapping single source (PLAN §9)", () => {
  const boardSource = readFileSync(resolve(__dirname, "Board.tsx"), "utf8");
  const viewSource = readFileSync(
    resolve(__dirname, "TaskListView.tsx"),
    "utf8",
  );

  it("the shared module owns the seven statuses in board order", () => {
    expect(COLUMN_STATUSES).toEqual([
      "planning",
      "todo",
      "doing",
      "review",
      "blocked",
      "done",
      "cancelled",
    ]);
    expect(new Set(Object.keys(STATUS_LABEL_KEYS))).toEqual(
      new Set(COLUMN_STATUSES),
    );
    expect(new Set(Object.keys(STATUS_COLORS))).toEqual(
      new Set(COLUMN_STATUSES),
    );
  });

  it.each([
    ["Board.tsx", boardSource],
    ["TaskListView.tsx", viewSource],
  ])("%s imports the mapping instead of copying it", (_name, source) => {
    expect(source).toContain('from "../utils/taskStatus"');
    for (const symbol of [
      "STATUS_LABEL_KEYS",
      "STATUS_COLORS",
      "COLUMN_STATUSES",
      "TERMINAL_STATUSES",
      "STATUS_TRANSITIONS",
    ]) {
      expect(source).not.toContain(`const ${symbol}`);
      expect(source).not.toContain(`function ${symbol}`);
    }
    // Neither file re-declares the transition table or its guard.
    expect(source).not.toContain("const isTransitionAllowed");
    expect(source).not.toContain("const asTaskStatus");
  });
});

describe("G1 分区卡片 + G4 标题可点（PLAN §4.1 FIND-11）", () => {
  it("AC-G1-1: 7 个分区各有一张卡片 testid，顺序 = COLUMN_STATUSES；空区仍保留卡片", async () => {
    mockTasks([
      task({ task_id: "tsk_1", title: "Alpha", status: "todo" }),
      task({ task_id: "tsk_2", title: "Beta", status: "doing", sort_order: 1 }),
    ]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_1");

    const ids = screen
      .getAllByTestId(/^task-section-card-/)
      .map((node) => node.getAttribute("data-testid") ?? "");
    assertSevenCards(ids);

    // 空区（5 个）仍有卡片 + 计数 0 + 空态文案。
    for (const status of COLUMN_STATUSES) {
      const hasTasks = status === "todo" || status === "doing";
      if (hasTasks) continue;
      expect(
        screen.getByTestId(`task-section-card-${status}`),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(`task-section-count-${status}`),
      ).toHaveTextContent("0");
      expect(
        screen.getByTestId(`task-section-empty-${status}`),
      ).toHaveTextContent("projects.taskListEmpty");
    }
  });

  it("③ 判别性对照（可复跑）：少一张 / 多一张 / 顺序错 → 卡片辅助函数必须失败", async () => {
    mockTasks([task({ task_id: "tsk_1", title: "Alpha" })]);
    renderList();
    await screen.findByTestId("task-row-title-tsk_1");
    const ids = screen
      .getAllByTestId(/^task-section-card-/)
      .map((node) => node.getAttribute("data-testid") ?? "");
    // 正例：真实 DOM 走同一套辅助函数 → 通过。
    expect(() => assertSevenCards(ids)).not.toThrow();
    // 反例：缺一张 / 多一张 / 顺序颠倒 → 必失败。
    expect(() => assertSevenCards(ids.slice(0, 6))).toThrow();
    expect(() =>
      assertSevenCards([...ids, "task-section-card-extra"]),
    ).toThrow();
    expect(() => assertSevenCards([...ids].reverse())).toThrow();
  });

  it("AC-G4-1: 标题是可点元素（非编辑入口）→ 点击调用 onOpenTask(task_id)", async () => {
    mockTasks([task({ task_id: "tsk_77", title: "Open me" })]);
    const onEditTask = vi.fn();
    const { onOpenTask } = renderList(undefined, onEditTask);
    const title = await screen.findByTestId("task-row-title-tsk_77");

    // 可点元素：button 或 role=link（本轮推翻批次三 S8(b) 的「纯文本」）。
    const clickable =
      title.tagName === "BUTTON" || title.getAttribute("role") === "link";
    expect(clickable).toBe(true);
    // 键盘可达：可聚焦 + aria-label 含任务标题。
    expect(title).toHaveAttribute("tabindex", "0");
    expect(title.getAttribute("aria-label")).toContain("Open me");

    await userEvent.click(title);
    expect(onOpenTask).toHaveBeenCalledWith("tsk_77");
    // ★ 标题**不是**编辑入口（S8(b) 保留的另一半）。
    expect(onEditTask).not.toHaveBeenCalled();
  });

  it("AC-G4-1: 标题键盘可达 —— Enter 与 Space 都能触发 onOpenTask", async () => {
    mockTasks([
      task({ task_id: "tsk_e", title: "Enter me" }),
      task({ task_id: "tsk_s", title: "Space me", sort_order: 1 }),
    ]);
    const { onOpenTask } = renderList();
    const enterTitle = await screen.findByTestId("task-row-title-tsk_e");

    enterTitle.focus();
    expect(document.activeElement).toBe(enterTitle);
    await userEvent.keyboard("{Enter}");
    expect(onOpenTask).toHaveBeenCalledWith("tsk_e");

    const spaceTitle = screen.getByTestId("task-row-title-tsk_s");
    spaceTitle.focus();
    await userEvent.keyboard(" ");
    expect(onOpenTask).toHaveBeenCalledWith("tsk_s");
  });

  it("AC-G4-1: 未传 onOpenTask 时标题退化（无假交互），编辑按钮仍在", async () => {
    mockTasks([task({ task_id: "tsk_9", title: "No open" })]);
    const onEditTask = vi.fn();
    render(<TaskListView projectId="prj_1" onEditTask={onEditTask} />);
    const title = await screen.findByTestId("task-row-title-tsk_9");
    expect(title.tagName).toBe("SPAN");
    // 编辑入口仍是独立图标按钮（不受标题形态影响）。
    const edit = screen.getByTestId("task-row-edit-tsk_9");
    await userEvent.click(edit);
    expect(onEditTask).toHaveBeenCalledWith("tsk_9");
  });
});
