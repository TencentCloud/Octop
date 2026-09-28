import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

// Only the transport is mocked: both pages must go through ``projectsApi`` /
// ``projectMetadataApi``, so asserting on ``request`` proves the real paths and
// request bodies (R4 field set, PLAN §6.3 wrapper reuse).
vi.mock("../../api/request", () => ({
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

// The shared setup mock hands out a *fresh* ``t`` on every render, which turns
// ``Detail/index.tsx``'s ``useCallback(load, [projectId, t])`` + ``useEffect``
// into an endless refetch loop ("Maximum update depth exceeded"). Real i18next
// keeps ``t`` stable, so this file pins a stable one and keeps ``t(key)`` →
// key so assertions stay on the frozen key names.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: unknown): string =>
    typeof fallback === "string" ? fallback : key;
  return {
    useTranslation: () => ({
      t,
      i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
    }),
    Trans: ({ children }: { children?: unknown }) => children,
  };
});

import { request } from "../../api/request";
import zh from "../../locales/zh.json";
import type { ProjectOut } from "../../api/modules/projects";
import ProjectsPage from "./index";
import ProjectDetailPage from "./Detail/index";

const mockedRequest = vi.mocked(request);

const PROJECT: ProjectOut = {
  project_id: "p1",
  name: "Website revamp",
  goal: "Ship v2",
  status: "cancelled",
  owner_user_id: 7,
  memory_namespace: "project-p1",
  kb_id: null,
  start_at: null,
  due_at: null,
  created_at: 1700000000,
  updated_at: 1700000000,
};

type Handler = (init?: RequestInit) => unknown;

let routes: Record<string, Handler>;

function callFor(method: string, path: string): [string, RequestInit] {
  const found = mockedRequest.mock.calls.find(
    ([called, init]) => called === path && (init?.method ?? "GET") === method,
  );
  expect(found, `${method} ${path} was never requested`).toBeTruthy();
  return found as [string, RequestInit];
}

function bodyOf(init: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init.body)) as Record<string, unknown>;
}

function renderRoutes(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function openCreateDialog() {
  renderRoutes("/projects");
  await waitFor(() => {
    expect(screen.getByText("Website revamp")).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button", { name: "projects.create" }));
  return screen.findByTestId("create-project-dialog");
}

beforeEach(() => {
  vi.clearAllMocks();
  routes = {
    "GET /settings/timezone": () => ({ timezone: "UTC" }),
    "GET /projects": () => [PROJECT],
    "POST /projects": () => PROJECT,
    "GET /projects/p1": () => PROJECT,
    "GET /projects/p1/members": () => [],
    "GET /projects/p1/tasks": () => [],
    "GET /projects/p1/tags": () => [],
    "GET /projects/p1/custom-fields": () => [],
  };
  mockedRequest.mockImplementation(
    async (path: string, init?: RequestInit): Promise<unknown> => {
      const method = init?.method ?? "GET";
      const handler = routes[`${method} ${path}`];
      if (!handler) throw new Error(`unexpected request: ${method} ${path}`);
      return handler(init);
    },
  );
});

describe("new-project dialog (R4 interaction alignment)", () => {
  it("shows the breadcrumb, inline title, description and chip toolbar", async () => {
    const dialog = await openCreateDialog();

    // The breadcrumb is the modal header (it also names the dialog).
    const breadcrumb = screen.getByTestId("create-project-breadcrumb");
    expect(breadcrumb.textContent).toContain("projects.title");
    expect(breadcrumb.textContent).toContain("projects.create");

    expect(
      within(dialog).getByTestId("create-project-name"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByTestId("create-project-goal"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "projects.chipStatus" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "projects.chipStartAt" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "projects.chipDueAt" }),
    ).toBeInTheDocument();
  });

  it("exposes exactly the five frozen fields and nothing else", async () => {
    const dialog = await openCreateDialog();

    const fields = Array.from(
      dialog.querySelectorAll('[data-testid^="create-project-field-"]'),
    ).map((node) => node.getAttribute("data-testid"));
    expect(fields).toEqual([
      "create-project-field-name",
      "create-project-field-goal",
      "create-project-field-status",
      "create-project-field-start",
      "create-project-field-due",
    ]);

    // R4 forbids priority / assignee / repository here. The repository field
    // has no key at all in the frozen table, so it cannot be rendered.
    for (const forbidden of [
      "projects.chipPriority",
      "projects.chipAssignee",
    ]) {
      expect(
        within(dialog).queryByRole("button", { name: forbidden }),
      ).not.toBeInTheDocument();
    }
  });

  it("submits the five aligned fields and never the three forbidden ones", async () => {
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByTestId("create-project-name"), {
      target: { value: "Website revamp" },
    });
    fireEvent.change(within(dialog).getByTestId("create-project-goal"), {
      target: { value: "Ship v2" },
    });
    // Drive the status chip's popover.
    fireEvent.click(
      within(dialog).getByRole("button", { name: "projects.chipStatus" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "projects.statusCancelled" }),
    );

    fireEvent.click(
      within(dialog.closest(".ant-modal") as HTMLElement).getByRole("button", {
        name: "common.create",
      }),
    );

    await waitFor(() => {
      expect(callFor("POST", "/projects")).toBeTruthy();
    });
    const body = bodyOf(callFor("POST", "/projects")[1]);
    expect(Object.keys(body).sort()).toEqual([
      "due_at",
      "goal",
      "name",
      "start_at",
      "status",
    ]);
    expect(body).toEqual({
      name: "Website revamp",
      goal: "Ship v2",
      status: "cancelled",
      start_at: null,
      due_at: null,
    });
  });

  it("offers six distinct status options and warns when archived is picked", async () => {
    const dialog = await openCreateDialog();

    fireEvent.click(
      within(dialog).getByRole("button", { name: "projects.chipStatus" }),
    );
    const menu = document.querySelector(".ant-popover") as HTMLElement;
    expect(menu).toBeTruthy();

    const optionTexts = Array.from(menu.querySelectorAll("button")).map(
      (node) => node.textContent,
    );
    expect(optionTexts).toHaveLength(6);
    expect(new Set(optionTexts).size).toBe(6);
    expect(
      within(menu).getByRole("button", { name: "projects.statusArchived" }),
    ).toBeInTheDocument();
    expect(
      within(menu).getByRole("button", { name: "projects.statusCancelled" }),
    ).toBeInTheDocument();

    // S-10: picking ``archived`` must surface the read-only hint.
    expect(
      within(dialog).queryByTestId("create-project-archived-hint"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      within(menu).getByRole("button", { name: "projects.statusArchived" }),
    );
    expect(
      await within(dialog).findByTestId("create-project-archived-hint"),
    ).toHaveTextContent("projects.archiveConfirmDesc");
  });

  it("reopens with a clean field set", async () => {
    const dialog = await openCreateDialog();
    fireEvent.change(within(dialog).getByTestId("create-project-name"), {
      target: { value: "Draft name" },
    });
    expect(within(dialog).getByTestId("create-project-name")).toHaveValue(
      "Draft name",
    );

    fireEvent.click(
      within(dialog.closest(".ant-modal") as HTMLElement).getByRole("button", {
        name: "common.cancel",
      }),
    );
    await waitFor(() => {
      expect(screen.queryByTestId("create-project-dialog")).toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: "projects.create" }));
    const reopened = await screen.findByTestId("create-project-dialog");
    expect(within(reopened).getByTestId("create-project-name")).toHaveValue("");
  });
});

describe("project status copy (AC-U-22 / AC-U-23)", () => {
  it("keeps all six zh values distinct — archived is not cancelled", () => {
    const copy = zh.projects as Record<string, string>;
    const keys = [
      "statusDraft",
      "statusActive",
      "statusPaused",
      "statusCompleted",
      "statusCancelled",
      "statusArchived",
    ];
    const values = keys.map((key) => copy[key]);
    for (const value of values) {
      expect(value).toBeTruthy();
    }
    expect(new Set(values).size).toBe(6);
    expect(copy.statusCancelled).not.toBe(copy.statusArchived);
  });

  it("renders the new status labels on the detail page", async () => {
    renderRoutes("/projects/p1");

    const statusTag = await screen.findByText("projects.statusCancelled");
    expect(statusTag).toBeInTheDocument();
  });
});

describe("project detail metadata mount (T-FE-META products)", () => {
  it("mounts the tag and custom-field definition panels", async () => {
    // PLAN §4.2：面板归 `tasks` Tab → 先进该 Tab 再断言（**只换进入方式**，
    // 两道读环断言与两行 callFor 原样保留 —— 它们是防死 schema 的唯一凭证）。
    renderRoutes("/projects/p1?tab=tasks");

    expect(await screen.findByTestId("project-tags")).toBeInTheDocument();
    expect(
      await screen.findByTestId("project-custom-fields"),
    ).toBeInTheDocument();
    // The read rings really ran (empty project → the panels' empty states).
    await waitFor(() => {
      expect(callFor("GET", "/projects/p1/tags")).toBeTruthy();
      expect(callFor("GET", "/projects/p1/custom-fields")).toBeTruthy();
    });
    expect(screen.getByText("projects.tagsEmpty")).toBeInTheDocument();
    expect(screen.getByText("projects.cfEmpty")).toBeInTheDocument();
  });
});

describe("project detail 4 tabs + right rail (T-FE-DETAIL)", () => {
  /** 探针：把当前 query string 渲染出来，用于断言 URL 真的（没）被改写。 */
  function LocationProbe() {
    const location = useLocation();
    return <span data-testid="location-search">{location.search}</span>;
  }

  function renderWithProbe(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/projects/:projectId"
            element={
              <>
                <ProjectDetailPage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
  }

  const planVisible = async () =>
    screen.findByText("projects.taskStatusPlanning");

  it("S5：无参数 → 落 plan，且不往 URL 写参数", async () => {
    renderWithProbe("/projects/p1");
    expect(await planVisible()).toBeInTheDocument();
    expect(screen.getByTestId("location-search")).toHaveTextContent("");
  });

  it("S5：?tab=bogus 非法值 → 落 plan，且不把非法值写回/写坏 URL", async () => {
    renderWithProbe("/projects/p1?tab=bogus");
    expect(await planVisible()).toBeInTheDocument();
    // 非法值既不生效也不被规范化写回 —— URL 原样保留（未被改写）。
    expect(screen.getByTestId("location-search")).toHaveTextContent(
      "?tab=bogus",
    );
    expect(
      screen.getByRole("tab", { name: "projects.tabPlan" }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("S5：?tab=assets → 直接落 assets；点击 Tab 用 replace 写 URL", async () => {
    renderWithProbe("/projects/p1?tab=assets");
    expect(
      await screen.findByTestId("project-assets-empty"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("location-search")).toHaveTextContent(
      "?tab=assets",
    );

    fireEvent.click(screen.getByRole("tab", { name: "projects.tabTasks" }));
    await waitFor(() =>
      expect(screen.getByTestId("location-search")).toHaveTextContent(
        "tab=tasks",
      ),
    );
  });

  it("四个 Tab 各自能渲染（plan / tasks / assets / dynamic）", async () => {
    renderWithProbe("/projects/p1?tab=plan");
    // plan = 既有看板（7 列，planning 在列首）。
    expect(await planVisible()).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "projects.tabTasks" }));
    expect(await screen.findByTestId("project-tags")).toBeInTheDocument();
    expect(
      await screen.findByTestId("project-custom-fields"),
    ).toBeInTheDocument();
    // F1 分区后该文案在 7 个空区各出现一次（PLAN F2 acceptance ⑧）。
    expect(await screen.findAllByText("projects.taskListEmpty")).toHaveLength(
      7,
    );
    // tasks Tab 里两道读环真的发出（同一份防死 schema 凭证）。
    await waitFor(() => {
      expect(callFor("GET", "/projects/p1/tags")).toBeTruthy();
      expect(callFor("GET", "/projects/p1/custom-fields")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("tab", { name: "projects.tabAssets" }));
    expect(
      await screen.findByTestId("project-assets-empty"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "projects.tabDynamic" }));
    expect(await screen.findByTestId("project-dynamic")).toBeInTheDocument();
    expect(screen.getByText("projects.dynamicPlaceholder")).toBeInTheDocument();
  });

  it("S6：右栏常驻（空数据不隐藏整栏），且 DOM 顺序 = 主区 → 右栏", async () => {
    renderWithProbe("/projects/p1");
    await planVisible();

    const tabList = screen.getByRole("tablist");
    const rail = screen.getByTestId("project-right-rail");
    expect(rail).toBeInTheDocument();
    // 主区在右栏**之前**（窄屏堆叠顺序即主区 → 右栏，不靠 CSS order）。
    expect(
      tabList.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // 空数据也照样渲染整栏：成员/专家面板给出各自的空态。
    expect(screen.getByText("projects.membersEmpty")).toBeInTheDocument();
    expect(screen.getByText("projects.expertNone")).toBeInTheDocument();
  });
});

describe("F2 概览压缩与主区归属（PLAN §2 / G6）", () => {
  function LocationProbeF2() {
    const location = useLocation();
    return <span data-testid="location-search">{location.search}</span>;
  }

  function renderF2(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/projects/:projectId"
            element={
              <>
                <ProjectDetailPage />
                <LocationProbeF2 />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("① 概览在右栏内（主区不再渲染），主区/概览/右栏各有 testid", async () => {
    renderF2("/projects/p1");
    await screen.findByTestId("project-overview");

    const main = screen.getByTestId("project-main-column");
    const overview = screen.getByTestId("project-overview");
    const rail = screen.getByTestId("project-right-rail");

    // ★ G2 改向（PLAN §2.3）：概览**已迁入右栏** → 主区不再渲染它（语义反转，非放宽）。
    expect(main.contains(overview)).toBe(false);
    // 保留②：主区与右栏是同一层级的两个 grid 子项（概览不得成为 grid 的直接子项）。
    expect(main.parentElement).toBe(rail.parentElement);
    // ★ G2 改向（PLAN §2.3）：概览在右栏之内。
    expect(rail.contains(overview)).toBe(true);
  });

  it("① 概览在 <TabBar> 之后（DOM 顺序：右栏在主区之后）", async () => {
    renderF2("/projects/p1");
    const overview = await screen.findByTestId("project-overview");
    const tabList = screen.getByRole("tablist");
    // ★ G2 改向（PLAN §2.3）：概览迁入右栏 → 顺序关系**方向反转**（仍显式断言顺序）。
    expect(
      tabList.compareDocumentPosition(overview) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("② 概览压缩为 6 项 + column=2；projectId / kbId 移出概览", async () => {
    const { container } = renderF2("/projects/p1");
    await screen.findByTestId("project-overview");

    const overview = screen.getByTestId("project-overview");
    const items = overview.querySelectorAll(".ant-descriptions-item");
    expect(items).toHaveLength(6);

    // 两列布局（antd 以 `ant-descriptions-row` 的列数体现，直接断 row 数量）。
    const rows = overview.querySelectorAll(".ant-descriptions-row");
    // goal 跨两列 → 其余 5 项两两成行 = 1 + 3 = 4 行。
    expect(rows).toHaveLength(4);

    // 6 项标签：目标 / 开始 / 截止 / 负责人 / 创建 / 更新。
    for (const key of [
      "projects.goal",
      "projects.startAt",
      "projects.dueAt",
      "projects.owner",
      "projects.createdAt",
      "projects.updatedAt",
    ]) {
      expect(within(overview).getByText(key)).toBeInTheDocument();
    }
    // 移出概览的两项（kbId 的独立编辑器由 F3 承载；projectId 进 title 属性）。
    expect(within(overview).queryByText("projects.projectId")).toBeNull();
    expect(within(overview).queryByText("projects.kbId")).toBeNull();
    // 数据源仍在：projectId 作为页面标题的 title 属性可达。
    expect(container.ownerDocument.querySelector('[title="p1"]')).toBeTruthy();
  });

  it("④⑥ 既有 4 Tab 与 ?tab= 语义不变，且 tablist 仍在右栏之前", async () => {
    renderF2("/projects/p1?tab=bogus");
    expect(
      await screen.findByText("projects.taskStatusPlanning"),
    ).toBeInTheDocument();

    const tabList = screen.getByRole("tablist");
    const rail = screen.getByTestId("project-right-rail");
    expect(
      tabList.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      Array.from(document.querySelectorAll('[role="tab"]')).map(
        (tab) => tab.textContent,
      ),
    ).toEqual([
      "projects.tabDynamic",
      "projects.tabPlan",
      "projects.tabTasks",
      "projects.tabAssets",
    ]);
  });
});

/** 详情接线用的一条任务（形状取自 `ProjectTask`，只填渲染需要的字段）。 */
const DETAIL_TASK = {
  task_id: "tsk_1",
  project_id: "p1",
  parent_id: null,
  title: "Detail me",
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
  created_at: 1_750_000_000,
  updated_at: 1_750_000_000,
};

describe("G2 概览入右栏 + 两个新组件接线（PLAN §2 / §4.1）", () => {
  function LocationProbeG2() {
    const location = useLocation();
    return <span data-testid="location-search">{location.search}</span>;
  }

  function renderG2(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/projects/:projectId"
            element={
              <>
                <ProjectDetailPage />
                <LocationProbeG2 />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("② 概览在右栏面板内（rail-overview）；主区原槽位 = QuickInput（在 TabBar 之上）", async () => {
    renderG2("/projects/p1");
    const railPanel = await screen.findByTestId("rail-overview");
    const overview = screen.getByTestId("project-overview");

    // 概览在第 7 面板之内，且该面板是右栏的第一个面板（置首）。
    expect(railPanel.contains(overview)).toBe(true);
    const rail = screen.getByTestId("project-right-rail");
    expect(within(rail).getAllByTestId(/^rail-/)[0]).toBe(railPanel);

    // 主区原槽位换成 QuickInput，且仍在 TabBar 之上。
    const quickInput = screen.getByTestId("project-quick-input");
    expect(screen.getByTestId("project-main-column").contains(quickInput)).toBe(
      true,
    );
    const tabList = screen.getByRole("tablist");
    expect(
      quickInput.compareDocumentPosition(tabList) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("⑤ ?tab=tasks&task=<id> → 详情面板替换任务列表；未命中 → taskDetailNotFound", async () => {
    routes["GET /projects/p1/tasks"] = () => [DETAIL_TASK];
    renderG2("/projects/p1?tab=tasks&task=tsk_1");

    expect(await screen.findByTestId("task-detail-panel")).toBeInTheDocument();
    // 列表被替换（不是叠加）。
    expect(screen.queryByTestId("project-task-list")).toBeNull();
  });

  it("⑤ 缺 tab 参数：?task=<id> 也进详情，且 tasks Tab 高亮", async () => {
    routes["GET /projects/p1/tasks"] = () => [DETAIL_TASK];
    renderG2("/projects/p1?task=tsk_1");

    expect(await screen.findByTestId("task-detail-panel")).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "projects.tabTasks" }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("⑤ 未命中的 task → 优雅降级（不白屏），返回后回到列表", async () => {
    routes["GET /projects/p1/tasks"] = () => [DETAIL_TASK];
    renderG2("/projects/p1?tab=tasks&task=tsk_missing");

    expect(
      await screen.findByTestId("task-detail-not-found"),
    ).toHaveTextContent("projects.taskDetailNotFound");
    fireEvent.click(screen.getByTestId("task-detail-back"));
    await waitFor(() =>
      expect(screen.getByTestId("location-search")).toHaveTextContent(
        "?tab=tasks",
      ),
    );
    expect(screen.queryByTestId("task-detail-panel")).toBeNull();
  });

  it("★ 端到端：点任务标题 → push ?tab=tasks&task=<id> → 详情渲染（openTask 已接线）", async () => {
    routes["GET /projects/p1/tasks"] = () => [DETAIL_TASK];
    renderG2("/projects/p1?tab=tasks");

    const title = await screen.findByTestId("task-row-title-tsk_1");
    fireEvent.click(title);

    expect(await screen.findByTestId("task-detail-panel")).toBeInTheDocument();
    const search = screen.getByTestId("location-search").textContent ?? "";
    expect(search).toContain("tab=tasks");
    expect(search).toContain("task=tsk_1");
  });
});
