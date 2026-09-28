import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import dayjs from "dayjs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

// Only the transport is mocked: the dialog must go through ``projectsApi`` /
// ``knowledgeBasesApi``, so asserting on ``request`` proves the real paths and
// the exact request bodies (PLAN §3 / §4.1).
vi.mock("../../api/request", () => ({
  request: vi.fn(),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
}));

const messageErrorMock = vi.fn();
const messageSuccessMock = vi.fn();

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: (...args: unknown[]) => messageErrorMock(...args),
    success: (...args: unknown[]) => messageSuccessMock(...args),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

let currentUser: { id: number; role: "admin" | "user" } | null = null;
vi.mock("../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => currentUser,
}));

import { request } from "../../api/request";
import type { KnowledgeBase } from "../../api/modules/knowledgeBases";
import type { ProjectOut } from "../../api/modules/projects";
import ProjectsPage from "./index";

const mockedRequest = vi.mocked(request);

const OWNER_ID = 7;

const PROJECT: ProjectOut = {
  project_id: "p1",
  name: "Website revamp",
  goal: "Ship v2",
  status: "active",
  owner_user_id: OWNER_ID,
  memory_namespace: "project-p1",
  kb_id: "kb_1",
  start_at: 1_750_000_000,
  due_at: 1_750_600_000,
  created_at: 1_700_000_000,
  updated_at: 1_700_000_000,
};

function base(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    id: "kb_1",
    owner_user_id: OWNER_ID,
    name: "Alpha KB",
    description: "",
    default_open: false,
    shared: false,
    icon_name: "",
    embedding_model: "m",
    embedding_dim: 3,
    doc_count: 0,
    max_documents: 100,
    created_at: 1,
    updated_at: 1,
    ...overrides,
  };
}

const MEMBERS = [
  {
    subject_type: "user" as const,
    subject_id: String(OWNER_ID),
    user_id: OWNER_ID,
    role: "owner" as const,
    created_at: 1,
  },
];

type Handler = (init?: RequestInit) => unknown;

let routes: Record<string, Handler>;

function callFor(method: string, path: string): [string, RequestInit] {
  const found = mockedRequest.mock.calls.find(
    ([called, init]) => called === path && (init?.method ?? "GET") === method,
  );
  expect(found, `${method} ${path} was never requested`).toBeTruthy();
  return found as [string, RequestInit];
}

function patchBody(): Record<string, unknown> {
  const [, init] = callFor("PATCH", "/projects/p1");
  return JSON.parse(String(init.body)) as Record<string, unknown>;
}

async function openEdit() {
  render(
    <MemoryRouter initialEntries={["/projects"]}>
      <ProjectsPage />
    </MemoryRouter>,
  );
  await waitFor(() => {
    expect(screen.getByText("Website revamp")).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
  return screen.findByTestId("create-project-dialog");
}

beforeEach(() => {
  vi.clearAllMocks();
  currentUser = { id: OWNER_ID, role: "user" };
  routes = {
    "GET /settings/timezone": () => ({ timezone: "UTC" }),
    "GET /projects": () => [PROJECT],
    "GET /projects/p1/members": () => MEMBERS,
    "GET /knowledge-bases": () => [
      base(),
      base({ id: "kb_2", name: "Beta KB" }),
      base({ id: "kb_3", name: "Foreign KB", owner_user_id: 999 }),
    ],
    "PATCH /projects/p1": () => PROJECT,
    "POST /projects": () => PROJECT,
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

describe("F3 project dialog — edit prefill (AC-F3-2)", () => {
  it("back-fills goal / start / due / knowledge base and switches the copy", async () => {
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Website revamp")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
    const dialog = await screen.findByTestId("create-project-dialog");

    expect(await screen.findByTestId("create-project-name")).toHaveValue(
      "Website revamp",
    );
    expect(screen.getByTestId("create-project-goal")).toHaveValue("Ship v2");
    // 编辑模式文案 = projects.update / common.save（create 仍是 projects.create）。
    expect(screen.getByTestId("create-project-breadcrumb")).toHaveTextContent(
      "projects.update",
    );
    // 已绑定 KB 的名称出现在 chip 摘要里。
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "projects.kbId" }),
      ).toHaveTextContent("Alpha KB");
    });
    expect(dialog).toBeInTheDocument();
  });
});

describe("F3 project dialog — kb_id 三态（PLAN §4.1）", () => {
  it("缺失 = 不动：只改 goal 时请求体不含 kb_id（否则整单被升级成 MANAGE_CONFIG）", async () => {
    await openEdit();
    const goal = await screen.findByTestId("create-project-goal");
    fireEvent.change(goal, { target: { value: "Ship v3" } });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(callFor("PATCH", "/projects/p1")).toBeTruthy());
    const body = patchBody();
    expect(body.goal).toBe("Ship v3");
    expect(Object.keys(body)).not.toContain("kb_id");
  });

  it("null = 解绑：projects.kbUnbind → kb_id: null", async () => {
    await openEdit();
    fireEvent.click(
      await screen.findByRole("button", { name: "projects.kbId" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "projects.kbUnbind" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(callFor("PATCH", "/projects/p1")).toBeTruthy());
    const body = patchBody();
    expect(Object.keys(body)).toContain("kb_id");
    expect(body.kb_id).toBeNull();
  });

  it("值 = 改绑：选中另一个可写 KB → kb_id: 该 id", async () => {
    await openEdit();
    fireEvent.click(
      await screen.findByRole("button", { name: "projects.kbId" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Beta KB" }));
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(callFor("PATCH", "/projects/p1")).toBeTruthy());
    expect(patchBody().kb_id).toBe("kb_2");
  });

  it("只列出当前用户可写的 KB（照 get_writable_base：owner 或平台 admin）", async () => {
    await openEdit();
    fireEvent.click(
      await screen.findByRole("button", { name: "projects.kbId" }),
    );
    await screen.findByRole("button", { name: "Beta KB" });

    expect(screen.queryByRole("button", { name: "Foreign KB" })).toBeNull();
  });
});

describe("F3 project dialog — 无权限时的 kb 字段（PLAN §4.3）", () => {
  beforeEach(() => {
    currentUser = { id: 42, role: "user" };
    routes["GET /projects/p1/members"] = () => [
      { ...MEMBERS[0], subject_id: String(OWNER_ID) },
      {
        subject_type: "user" as const,
        subject_id: "42",
        user_id: 42,
        role: "member" as const,
        created_at: 2,
      },
    ];
  });

  it("member：chip 禁用 + 常显说明，且改 goal 仍可提交（请求体不含 kb_id）", async () => {
    await openEdit();

    const chip = await screen.findByRole("button", {
      name: "common.noPermission",
    });
    expect(chip).toHaveAttribute("aria-disabled", "true");
    // 说明是常显文本，不只是 tooltip。
    expect(screen.getByTestId("kb-readonly-hint")).toHaveTextContent(
      "common.noPermission",
    );
    // 禁用的 chip 不弹 popover：点它不会出现任何 KB 选项。
    fireEvent.click(chip);
    expect(screen.queryByRole("button", { name: "Beta KB" })).toBeNull();

    const goal = screen.getByTestId("create-project-goal");
    fireEvent.change(goal, { target: { value: "member edit" } });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(callFor("PATCH", "/projects/p1")).toBeTruthy());
    const body = patchBody();
    expect(body.goal).toBe("member edit");
    // ★ 关键：member 的正常编辑必须仍走 PROJECT_WRITE，不被升级成 MANAGE_CONFIG。
    expect(Object.keys(body)).not.toContain("kb_id");
    expect(messageErrorMock).not.toHaveBeenCalled();
  });
});

describe("F3 project dialog — 清空语义与日期边界（PLAN §3）", () => {
  it('goal 清空 = goal: ""；日期清空 = clear_* 标志（不是 null 覆盖）', async () => {
    await openEdit();
    fireEvent.change(await screen.findByTestId("create-project-goal"), {
      target: { value: "   " },
    });

    // 打开两个日期 chip 并点各自的清除按钮（antd 的 .ant-picker-clear）。
    for (const aria of ["projects.chipStartAt", "projects.chipDueAt"]) {
      fireEvent.click(screen.getByRole("button", { name: aria }));
      const clear = await waitFor(() => {
        const found = document.querySelector(".ant-picker-clear");
        expect(found).toBeTruthy();
        return found as HTMLElement;
      });
      fireEvent.click(clear);
    }

    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(callFor("PATCH", "/projects/p1")).toBeTruthy());
    const body = patchBody();
    expect(body.goal).toBe("");
    expect(body.clear_start_at).toBe(true);
    expect(body.clear_due_at).toBe(true);
    expect(body.start_at).toBeNull();
    expect(body.due_at).toBeNull();
  });

  it("due < start 时前端阻止提交并提示", async () => {
    // 反序的现值同样走 onFinish 的 values，因此这一条直接覆盖提交前校验。
    routes["GET /projects"] = () => [
      { ...PROJECT, start_at: 1_760_000_000, due_at: 1_750_600_000 },
    ];
    await openEdit();

    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(messageErrorMock).toHaveBeenCalled());
    expect(messageErrorMock.mock.calls[0][0]).toBe(
      "apiErrors.PROJECT_TASK_DATE_INVALID",
    );
    expect(
      mockedRequest.mock.calls.some(([, init]) => init?.method === "PATCH"),
    ).toBe(false);
  });

  // The date case types into antd's picker; with the default per-keystroke
  // ``setTimeout(0)``+await each character costs a timer turn, and under six
  // competing workers that alone can eat vitest's 5s per-test budget before the
  // commit wait below is ever reached (V1 round 2: still 2 red in 6 full runs
  // *with* the extended waitFor). ``delay: null`` types without the waits, and
  // the explicit test budget keeps the wall clock from failing the case.
  it("改开始日期后按 Unix 秒提交（前端日期选择器 → 秒）", async () => {
    const user = userEvent.setup({ delay: null });
    await openEdit();

    fireEvent.click(
      screen.getByRole("button", { name: "projects.chipStartAt" }),
    );
    const input = await waitFor(() => {
      const found = document.querySelector(
        ".ant-picker-input input",
      ) as HTMLInputElement | null;
      expect(found).toBeTruthy();
      return found as HTMLInputElement;
    });
    await user.clear(input);
    await user.type(input, "2025-01-02 03:04{enter}");
    // ★ Race guard (T-REG4 / V1 round 2): Enter only *starts* rc-picker's
    //   parse-then-commit path, and the input already shows the typed text —
    //   waiting on the input would prove nothing. Wait for the chip summary:
    //   it renders the form value (`Form.useWatch("start_at")`), so it changes
    //   only once the parsed date is really in the store (the T-REG4 mutation
    //   probe showed this condition is not vacuous).
    //   ★ 1000 ms (the `waitFor` default) is not a safe upper bound for a full
    //   run: the commit is asynchronous and six workers share the CPU.
    await waitFor(
      () =>
        expect(
          screen.getByRole("button", { name: /projects\.chipStartAt/ }),
        ).toHaveTextContent("2025-01-02 03:04"),
      { timeout: 5000 },
    );
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(callFor("PATCH", "/projects/p1")).toBeTruthy());
    expect(patchBody().start_at).toBe(
      dayjs("2025-01-02 03:04", "YYYY-MM-DD HH:mm").unix(),
    );
  }, 20_000);
});

describe("F3 project dialog — 提交后重读与新建回归", () => {
  it("编辑成功后重读项目列表（非本地乐观改）", async () => {
    await openEdit();
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(callFor("PATCH", "/projects/p1")).toBeTruthy());
    await waitFor(() => {
      const lists = mockedRequest.mock.calls.filter(
        ([path, init]) =>
          path === "/projects" && (init?.method ?? "GET") === "GET",
      );
      // 初次加载 + 提交后重读。
      expect(lists.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("新建模式仍提交 goal / start_at / due_at，且不含 kb_id", async () => {
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Website revamp")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "projects.create" }));
    const dialog = await screen.findByTestId("create-project-dialog");

    fireEvent.change(screen.getByTestId("create-project-name"), {
      target: { value: "New one" },
    });
    fireEvent.change(screen.getByTestId("create-project-goal"), {
      target: { value: "A goal" },
    });
    // 新建模式没有 KB 字段（ProjectCreate 不接受 kb_id）。
    expect(dialog).toBeInTheDocument();
    expect(screen.queryByTestId("create-project-field-kb")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "common.create" }));

    await waitFor(() => expect(callFor("POST", "/projects")).toBeTruthy());
    const body = JSON.parse(
      String(callFor("POST", "/projects")[1].body),
    ) as Record<string, unknown>;
    expect(body).toMatchObject({
      name: "New one",
      goal: "A goal",
      status: "draft",
      start_at: null,
      due_at: null,
    });
    expect(Object.keys(body)).not.toContain("kb_id");
  });
});
