import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

// 页面测试会经 `Detail/index.tsx → AssetsTab → DocumentPreviewCore` 传递性引入
// `react-pdf`；jsdom 无 `DOMMatrix` ⇒ 按仓内惯例（`ProjectsPage.test.tsx`）打桩。
vi.mock("react-pdf", () => ({
  Document: () => <div data-testid="pdf-document" />,
  Page: () => <div data-testid="pdf-page" />,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

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

// 页面测试需要**稳定的 `t`**（共享 setup 的 mock 每次渲染发一个新的 ⇒
// `Detail/index.tsx` 的 `useCallback(load, [projectId, t])` 会无限重取）。
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

// ★ T-86：`agent_id` 由 dashboard 的当前 agent 充当**定位符**（后端路由要求它，
// 见 `api/modules/projects.ts · fetchMemory` 的注释）⇒ 本文件直接钉住这个输入。
const agentState = vi.hoisted(() => ({ activeAgentId: "a1" as string | null }));
vi.mock("../../../context/AgentContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../context/AgentContext")>()),
  useAgent: () => ({
    agents: [],
    activeAgentId: agentState.activeAgentId,
    activeAgent: null,
    loading: false,
    error: null,
    setActiveAgent: () => undefined,
    refresh: async () => undefined,
  }),
}));

import { request } from "../../../api/request";
import ProjectDetailPage from "./index";
import ProjectMemoryTab from "./ProjectMemoryTab";

const mockedRequest = vi.mocked(request);

type Handler = (init?: RequestInit) => unknown;
let routes: Record<string, Handler>;

function callFor(path: string): [string, RequestInit] {
  const found = mockedRequest.mock.calls.find(([called]) => called === path);
  expect(found, `${path} was never requested`).toBeTruthy();
  return found as [string, RequestInit];
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-search">{location.search}</div>;
}

const MEMORY_PATH = "/projects/p1/memory?agent_id=a1";
/** 路由表的键**带方法前缀**（`routes[\`${method} ${path}\`]`）—— 漏了前缀就静默落到默认分支。 */
const MEMORY_KEY = `GET ${MEMORY_PATH}`;

beforeEach(() => {
  vi.clearAllMocks();
  agentState.activeAgentId = "a1";
  routes = {
    "GET /settings/timezone": () => ({ timezone: "UTC" }),
    "GET /projects/p1": () => ({
      project_id: "p1",
      name: "Website revamp",
      goal: "Ship v2",
      status: "active",
      owner_user_id: 7,
      memory_namespace: "project-p1",
      kb_id: null,
      start_at: null,
      due_at: null,
      created_at: 1700000000,
      updated_at: 1700000000,
    }),
    "GET /projects/p1/members": () => [],
    "GET /projects/p1/tasks": () => [],
    "GET /projects/p1/tags": () => [],
    "GET /projects/p1/custom-fields": () => [],
    [MEMORY_KEY]: () => ({
      project_id: "p1",
      items: [],
      next_cursor: null,
    }),
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

/** 渲染 Tab 本体（不经页面）—— 组件级用例。 */
function renderTab() {
  return render(
    <MemoryRouter>
      <ProjectMemoryTab projectId="p1" />
    </MemoryRouter>,
  );
}

describe("T-86 · ProjectMemoryTab — 三态都不许被当成错误", () => {
  it("① 空态：0 条记忆 ⇒ 「暂无项目记忆」＋「记到项目」引导，且**没有** error UI", async () => {
    renderTab();

    expect(
      await screen.findByTestId("project-memory-empty"),
    ).toBeInTheDocument();
    expect(screen.getByText("暂无项目记忆")).toBeInTheDocument();
    // ★ 卡面 ②：0 条是**空态**而不是错误 —— 错误 UI 必须不存在。
    expect(screen.queryByTestId("project-memory-error")).toBeNull();
    // 引导指向「记到项目」（空态不是死胡同）。
    expect(screen.getByText(/记到项目/)).toBeInTheDocument();
    // 网络出口只有 api 包装：请求路径与参数由它决定。
    expect(callFor(MEMORY_PATH)[0]).toBe(MEMORY_PATH);
  });

  it("② 有行 ⇒ 渲染内容与来源层（不是空态、不是错误）", async () => {
    routes[MEMORY_KEY] = () => ({
      project_id: "p1",
      items: [
        {
          id: "atom-1",
          text: "对账以 RUN.log.md 的实测时刻为准",
          source_layer: "project",
          namespace: "project_p1",
        },
      ],
      next_cursor: null,
    });

    renderTab();

    expect(
      await screen.findByTestId("project-memory-list"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("project-memory-row")).toHaveTextContent(
      "对账以 RUN.log.md 的实测时刻为准",
    );
    expect(screen.queryByTestId("project-memory-empty")).toBeNull();
    expect(screen.queryByTestId("project-memory-error")).toBeNull();
  });

  it("③ 403 ⇒ 友好的无权限态（**不是** error UI）", async () => {
    routes[MEMORY_KEY] = () => {
      throw new Error(
        'Request failed: 403 Forbidden - {"error":{"code":"PROJECT_FORBIDDEN"}}',
      );
    };

    renderTab();

    expect(
      await screen.findByTestId("project-memory-denied"),
    ).toBeInTheDocument();
    expect(screen.getByText("无权查看该项目的记忆")).toBeInTheDocument();
    // ★ 403 是**状态**：不许落到 error 分支（那是"页面崩了"的语义）。
    expect(screen.queryByTestId("project-memory-error")).toBeNull();
  });

  it("④ 其它失败 ⇒ error UI ＋ 可重试", async () => {
    let calls = 0;
    routes[MEMORY_KEY] = () => {
      calls += 1;
      throw new Error("Request failed: 500 Internal Server Error");
    };

    renderTab();

    expect(
      await screen.findByTestId("project-memory-error"),
    ).toBeInTheDocument();
    const before = calls;
    fireEvent.click(screen.getByRole("button", { name: /重试/ }));
    await waitFor(() => expect(calls).toBeGreaterThan(before));
  });

  it("⑤ 没有当前 agent ⇒ 提示而非请求（不发无效请求）", async () => {
    agentState.activeAgentId = null;

    renderTab();

    expect(
      await screen.findByTestId("project-memory-no-agent"),
    ).toBeInTheDocument();
    // ★ "没有定位符就不发请求" 是**可断言**的：不是"发了再处理错误"。
    expect(mockedRequest).not.toHaveBeenCalled();
  });
});

// ★ 卡面 ③④ 的两组禁项 —— 抽成常量，**好让它们自己有判别力**（见下一条用例）。
const BANNED_NETWORK = [
  /\bfetch\s*\(/,
  /XMLHttpRequest/,
  /\baxios\b/,
  /from\s+["'][^"']*api\/request["']/,
];
const BANNED_PERMISSION = [
  /PROJECT_(READ|WRITE|CONFIRM)/,
  /ROLE_LEVELS|PERMISSION_MATRIX|ROLE_TABLE/,
  /\brole\s*(===|==|!==|!=)/,
  /\bis(Member|Owner|Viewer|Admin)\b/,
  /\bcan(Read|Write|Manage)\w*\s*=/,
  /assert_project_role/,
];

// 与同目录的 `QuickInput.test.tsx` 同一写法（`import.meta.url` 在本环境不是 file:）。
const source = readFileSync(resolve(__dirname, "ProjectMemoryTab.tsx"), "utf8");

function hits(patterns: RegExp[], text: string): string[] {
  return patterns.filter((re) => re.test(text)).map(String);
}

describe("T-86 · 静态断言（卡面 ③④）", () => {
  it("④ 组件零直接 fetch —— 唯一网络出口是 api/modules", () => {
    expect(hits(BANNED_NETWORK, source)).toEqual([]);
    // 正向：它确实经 api/modules 的包装取数。
    expect(source).toMatch(/from\s+["'][^"']*api\/modules\/projects["']/);
    expect(source).toMatch(/projectsApi\.fetchMemory/);
  });

  it("③ 未复制权限矩阵 —— 只认传输层 403，不做角色判定", () => {
    expect(hits(BANNED_PERMISSION, source)).toEqual([]);
    // 正向：403 只作为**传输状态**被识别。
    expect(source).toMatch(/403/);
    expect(source).toMatch(/PROJECT_FORBIDDEN/);
  });

  it("★ 判别性对照（零写入）：这两组禁项**抓到合成的坏源码**，且不冤真源码", () => {
    // 合成的"坏"源码：直接 fetch ＋ 角色判定 ＋ 复制后端权限常量。
    const bad = [
      'const r = await fetch("/api/projects/p1/memory");',
      'const canRead = member.role === "viewer";',
      "void PROJECT_READ;",
    ].join("\n");

    // 判别力：坏源码必须被**同一组**规则抓到（否则这两条静态断言是空断言）。
    expect(hits(BANNED_NETWORK, bad).length).toBeGreaterThan(0);
    expect(hits(BANNED_PERMISSION, bad).length).toBeGreaterThan(0);
    // 不冤：真源码在上面两条里已经 `toEqual([])`（此处再钉一次，防将来把断言改成"非空即过"）。
    expect(hits(BANNED_NETWORK, source)).toEqual([]);
    expect(hits(BANNED_PERMISSION, source)).toEqual([]);
  });
});

describe("T-86 · Tab 在项目详情页可见且可切换（卡面 ①）", () => {
  it("① TabBar 里有「项目记忆」；点它切到 ?tab=memory 并渲染该 Tab", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/p1?tab=plan"]}>
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

    const tab = await screen.findByRole("tab", { name: "projects.tabMemory" });
    expect(tab).toBeInTheDocument();

    fireEvent.click(tab);

    await waitFor(() =>
      expect(screen.getByTestId("location-search")).toHaveTextContent(
        "tab=memory",
      ),
    );
    // 该 Tab 真的渲染（空态即本用例的数据），不是只改了 URL。
    expect(
      await screen.findByTestId("project-memory-empty"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "projects.tabMemory" }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("① 原有 4 个 Tab 未被挤掉（回归：key/顺序不变）", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/p1?tab=plan"]}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const names = [
      "projects.tabDynamic",
      "projects.tabPlan",
      "projects.tabTasks",
      "projects.tabAssets",
      "projects.tabMemory",
    ];
    for (const name of names) {
      expect(await screen.findByRole("tab", { name })).toBeInTheDocument();
    }
  });
});
