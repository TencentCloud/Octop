import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
import type { ProjectTask } from "../../../api/modules/projects";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import {
  COLUMN_STATUSES,
  STATUS_COLORS,
  STATUS_LABEL_KEYS,
} from "../utils/taskStatus";
import TaskListView from "./TaskListView";

const mockedRequest = vi.mocked(request);

const START_AT = 1_750_000_000;
const DUE_AT = 1_750_600_000;
const UPDATED_AT = 1_750_900_000;

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

function renderList(tasks: ProjectTask[], refreshKey?: number) {
  const onOpenTask = vi.fn();
  const view = render(
    <TaskListView
      projectId="prj_1"
      onOpenTask={onOpenTask}
      refreshKey={refreshKey}
    />,
  );
  return { onOpenTask, view };
}

/** Rendered title buttons, i.e. the row order the user sees. */
function rowTitles(): string[] {
  return Array.from(
    document.querySelectorAll(".ant-table-tbody .ant-table-row"),
  )
    .map((row) => row.querySelector("button")?.textContent ?? "")
    .filter(Boolean);
}

function headerTitles(): string[] {
  return Array.from(document.querySelectorAll(".ant-table-thead th")).map(
    (cell) => cell.textContent ?? "",
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedRequest.mockImplementation(async (path: string) => {
    if (path === "/settings/timezone") return { timezone: "UTC" };
    if (path === "/projects/prj_1/tasks") return [];
    throw new Error(`unexpected request: ${path}`);
  });
});

describe("TaskListView", () => {
  it("renders the eight frozen columns from the shared status vocabulary", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/settings/timezone") return { timezone: "UTC" };
      if (path === "/projects/prj_1/tasks") {
        return [
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
        ];
      }
      throw new Error(`unexpected request: ${path}`);
    });

    renderList([]);

    await waitFor(() => {
      expect(screen.getByText("Ship it")).toBeInTheDocument();
    });
    expect(headerTitles()).toEqual(COLUMN_KEYS);
    expect(COLUMN_KEYS).toHaveLength(8);

    // Status cell: shared label key + shared antd colour.
    const statusTag = screen.getByText(STATUS_LABEL_KEYS.doing);
    expect(statusTag).toHaveClass(`ant-tag-${STATUS_COLORS.doing}`);

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

  it("opens the task through onOpenTask", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/settings/timezone") return { timezone: "UTC" };
      if (path === "/projects/prj_1/tasks") {
        return [task({ task_id: "tsk_42", title: "Open me" })];
      }
      throw new Error(`unexpected request: ${path}`);
    });

    const { onOpenTask } = renderList([]);
    fireEvent.click(await screen.findByRole("button", { name: "Open me" }));

    expect(onOpenTask).toHaveBeenCalledWith("tsk_42");
  });

  it("sorts by (sort_order, task_id) so ties are deterministic (S7)", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/settings/timezone") return { timezone: "UTC" };
      if (path === "/projects/prj_1/tasks") {
        // Deliberately unsorted, and two rows share sort_order 5.
        return [
          task({ task_id: "tsk_b", title: "B", sort_order: 5 }),
          task({ task_id: "tsk_c", title: "C", sort_order: 1 }),
          task({ task_id: "tsk_a", title: "A", sort_order: 5 }),
        ];
      }
      throw new Error(`unexpected request: ${path}`);
    });

    renderList([]);

    await waitFor(() => {
      expect(rowTitles()).toEqual(["C", "A", "B"]);
    });
  });

  it("filters by status, with every status selected by default", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/settings/timezone") return { timezone: "UTC" };
      if (path === "/projects/prj_1/tasks") {
        return [
          task({ task_id: "tsk_1", title: "Todo task", status: "todo" }),
          task({
            task_id: "tsk_2",
            title: "Doing task",
            status: "doing",
            sort_order: 1,
          }),
        ];
      }
      throw new Error(`unexpected request: ${path}`);
    });

    renderList([]);
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

  it("filters by keyword across title and description, then shows the empty state", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/settings/timezone") return { timezone: "UTC" };
      if (path === "/projects/prj_1/tasks") {
        return [
          task({ task_id: "tsk_1", title: "Alpha", description: "first" }),
          task({
            task_id: "tsk_2",
            title: "Beta",
            description: "mentions gamma",
            sort_order: 1,
          }),
        ];
      }
      throw new Error(`unexpected request: ${path}`);
    });

    renderList([]);
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

    // No match → the frozen empty state.
    fireEvent.change(keyword, { target: { value: "nothing" } });
    expect(
      await screen.findByText("projects.taskListEmpty"),
    ).toBeInTheDocument();
    expect(document.querySelector(".ant-table-tbody")).toBeNull();
  });

  it("shows the empty state when the project has no tasks", async () => {
    renderList([]);

    expect(
      await screen.findByText("projects.taskListEmpty"),
    ).toBeInTheDocument();
    expect(screen.queryByText("projects.taskListColumnStatus")).toBeNull();
  });

  it("re-reads when the parent bumps refreshKey", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path === "/settings/timezone") return { timezone: "UTC" };
      if (path === "/projects/prj_1/tasks") {
        return [task({ task_id: "tsk_1", title: "First" })];
      }
      throw new Error(`unexpected request: ${path}`);
    });

    const { view } = renderList([], 0);
    await screen.findByText("First");
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
