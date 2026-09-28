import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// 只 mock 传输层：真跑 projectsApi 的 wrapper ⇒ 断言请求路径/方法逐字正确。
vi.mock("../../../api/request", () => ({
  request: vi.fn(),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
}));
// ★ i18n 用**真 zh.json** 解析（仓内 S10 惯例，与 `RailPanels.test.tsx` 同款）：
// 结论文本要断言【名字进入可见文本】，而全局 key-mock **不插值** ⇒ 必须真 zh。
vi.mock("react-i18next", async () => {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const zh = JSON.parse(
    fs.readFileSync(
      path.resolve(process.cwd(), "src/locales/zh.json"),
      "utf-8",
    ),
  ) as Record<string, unknown>;
  const lookup = (key: string): string | undefined => {
    let node: unknown = zh;
    for (const part of key.split(".")) {
      if (node === null || typeof node !== "object") return undefined;
      node = (node as Record<string, unknown>)[part];
    }
    return typeof node === "string" ? node : undefined;
  };
  const interpolate = (tpl: string, opts?: Record<string, unknown>) =>
    opts
      ? tpl.replace(/\{\{(\w+)\}\}/g, (m, n: string) =>
          n in opts ? String(opts[n]) : m,
        )
      : tpl;
  return {
    useTranslation: () => ({
      t: (key: string, fallback?: unknown, opts?: unknown) => {
        const options = (
          fallback !== null && typeof fallback === "object" ? fallback : opts
        ) as Record<string, unknown> | undefined;
        const template =
          lookup(key) ?? (typeof fallback === "string" ? fallback : undefined);
        return template === undefined ? key : interpolate(template, options);
      },
      i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
    }),
    Trans: ({ children }: { children?: unknown }) => children,
  };
});

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));
/* `useCurrentUser` 读 React context（无网络）⇒ 边界 mock 注入登录身份，
   与批次六 `AgentContext` 的 mock 同级；不改被测组件的取值路径。 */
vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1, username: "admin" }),
}));

vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

import { request, requestUpload } from "../../../api/request";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import DynamicTab from "./DynamicTab";

const mockedRequest = vi.mocked(request);
const mockedUpload = vi.mocked(requestUpload);

const COMMENT = {
  comment_id: "cmt_1",
  project_id: "p1",
  task_id: null,
  thread_id: null,
  author_type: "user",
  author_id: "admin",
  body: "第一条留言",
  source: "web",
  node_type: "none",
  concluded: false,
  created_at: 1_750_000_000,
  updated_at: 1_750_000_000,
};

const MEMBER = {
  subject_type: "user",
  subject_id: "u1",
  user_id: 1,
  role: "owner",
  name: "admin",
  created_at: 1,
};

let comments: unknown[] = [];

beforeEach(() => {
  comments = [];
  mockedRequest.mockReset();
  mockedRequest.mockImplementation(async (path: string, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    if (path === "/projects/p1/comments" && method === "POST")
      return COMMENT as never;
    // ★ 作用域调整（批次十二 F）：列表端点现在带查询串（`relevance` / `author_id` /
    //   `author_type`）⇒ GET 按【端点前缀】匹配（不再是精确串）；POST/conclude 仍精确匹配。
    if (path.startsWith("/projects/p1/comments") && method === "GET")
      return comments as never;
    if (path.endsWith("/conclude"))
      return { ...COMMENT, concluded: true } as never;
    if (path === "/projects/p1/members") return [MEMBER] as never;
    if (path === "/auth/me") return { id: 1, username: "admin" } as never;
    return null as never;
  });
});

function renderTab() {
  return render(
    <MemoryRouter initialEntries={["/projects/p1"]}>
      <Routes>
        <Route path="/projects/:projectId" element={<DynamicTab />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("动态 Tab = 项目留言 feed（批次八 AC-A-1..A-4）", () => {
  it("AC-A-1：有 composer；发布调用 POST /projects/p1/comments（正文）", async () => {
    renderTab();
    const composer = await screen.findByTestId("feed-composer");
    const input = within(composer).getByPlaceholderText("写点什么…");
    fireEvent.change(input, { target: { value: "新留言" } });
    fireEvent.click(within(composer).getByText("发布"));

    await waitFor(() => {
      const post = mockedRequest.mock.calls.find(
        ([path, init]) =>
          path === "/projects/p1/comments" &&
          (init as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeTruthy();
      expect(JSON.parse(String((post?.[1] as RequestInit).body))).toEqual({
        body: "新留言",
      });
    });
  });

  it("AC-A-2：feed-item 数量 == 接口返回条数；含作者/时间（服务器时区）/正文", async () => {
    comments = [
      COMMENT,
      { ...COMMENT, comment_id: "cmt_2", body: "第二条", author_id: "bob" },
    ];
    renderTab();

    await waitFor(() =>
      expect(screen.getAllByTestId("feed-item")).toHaveLength(2),
    );
    const first = screen.getAllByTestId("feed-item")[0];
    expect(first).toHaveTextContent("第一条留言");
    expect(first).toHaveTextContent("user:admin");
    expect(first).toHaveTextContent(formatServerDateTime(1_750_000_000, "UTC"));
  });

  it("AC-A-3：结论徽标 + 采纳走 POST conclude / 取消走 DELETE conclude", async () => {
    comments = [COMMENT];
    renderTab();
    const item = (await screen.findAllByTestId("feed-item"))[0];
    expect(within(item).queryByTestId("comment-conclusion-badge")).toBeNull();

    // 点击前先让「下一次读」返回已采纳形态（POST 后组件会 refresh）。
    comments = [{ ...COMMENT, concluded: true, node_type: "conclusion" }];
    fireEvent.click(within(item).getByText("采纳为结论"));
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.some(
          ([path, init]) =>
            path === "/projects/p1/comments/cmt_1/conclude" &&
            (init as RequestInit | undefined)?.method === "POST",
        ),
      ).toBe(true),
    );

    const concluded = (await screen.findAllByTestId("feed-item"))[0];
    expect(
      within(concluded).getByTestId("comment-conclusion-badge"),
    ).toBeInTheDocument();
    fireEvent.click(within(concluded).getByText("取消采纳"));
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.some(
          ([path, init]) =>
            path === "/projects/p1/comments/cmt_1/conclude" &&
            (init as RequestInit | undefined)?.method === "DELETE",
        ),
      ).toBe(true),
    );
  });

  it("★ 作者显示【名字】而不是裸 id；名字缺失 ⇒ 回退 type:id（不得空白）", async () => {
    comments = [
      { ...COMMENT, comment_id: "c_named", name: "张三", author_id: "1" },
      {
        ...COMMENT,
        comment_id: "c_bare",
        name: null,
        author_type: "agent",
        author_id: "agt_9",
      },
    ];
    renderTab();

    const items = await screen.findAllByTestId("feed-item");
    const named = within(items[0]).getByTestId("feed-author");
    expect(named).toHaveTextContent("张三");
    expect(named).not.toHaveTextContent("user:1"); // 不显示裸标识
    const bare = within(items[1]).getByTestId("feed-author");
    expect(bare).toHaveTextContent("agent:agt_9"); // 回退（不得空白）
    expect(bare.textContent?.trim()).not.toBe("");
  });

  it("AC-A-7：无留言 → feed-empty（不报错、不空白）", async () => {
    renderTab();
    expect(await screen.findByTestId("feed-empty")).toHaveTextContent(
      "暂无留言",
    );
    expect(screen.queryAllByTestId("feed-item")).toHaveLength(0);
  });

  it("★ O4：占位文案【键保留但不再渲染】", async () => {
    renderTab();
    await screen.findByTestId("feed-empty");
    expect(screen.queryByText("动态流即将上线")).toBeNull();
    expect(screen.queryByText("排入下一批")).toBeNull();
  });
});

describe("结论归属（P3 展示形态 / P3b 显示口径 / L30）", () => {
  it("① 名字可用 → 「结论 · 由 <名字> 采纳」（文本，非 tooltip）", async () => {
    comments = [
      {
        ...COMMENT,
        concluded: true,
        node_type: "conclusion",
        concluded_by_type: "user",
        concluded_by_id: "7",
        concluded_by_name: "张三",
      },
    ];
    renderTab();

    const by = await screen.findByTestId("comment-conclusion-by");
    expect(by).toHaveTextContent("结论 · 由 张三 采纳");
    // 既有徽标 testid 保留 ✓
    expect(screen.getByTestId("comment-conclusion-badge")).toBeInTheDocument();
  });

  it("② 名字拿不到 → 回退 `type:id`（★ 仍可区分「谁」）", async () => {
    comments = [
      {
        ...COMMENT,
        comment_id: "c_a",
        concluded: true,
        concluded_by_type: "user",
        concluded_by_id: "42",
        concluded_by_name: null,
      },
    ];
    renderTab();
    expect(
      await screen.findByTestId("comment-conclusion-by"),
    ).toHaveTextContent("结论 · 由 user:42 采纳");
  });

  it("③ 连 id 都没有 → 「已注销用户」（**不得空白**）", async () => {
    comments = [
      {
        ...COMMENT,
        concluded: true,
        concluded_by_type: null,
        concluded_by_id: null,
        concluded_by_name: null,
      },
    ];
    renderTab();
    const by = await screen.findByTestId("comment-conclusion-by");
    expect(by).toHaveTextContent("已注销用户");
    expect(by.textContent?.trim()).not.toBe("");
  });

  it("★ 可区分性：两位不同采纳者 ⇒ 文本不同（回退也不许退化成同一占位）", async () => {
    comments = [
      {
        ...COMMENT,
        comment_id: "c1",
        concluded: true,
        concluded_by_type: "user",
        concluded_by_id: "1",
        concluded_by_name: null,
      },
      {
        ...COMMENT,
        comment_id: "c2",
        concluded: true,
        concluded_by_type: "user",
        concluded_by_id: "2",
        concluded_by_name: null,
      },
    ];
    renderTab();
    const labels = (await screen.findAllByTestId("comment-conclusion-by")).map(
      (node) => node.textContent,
    );
    expect(labels).toEqual(["结论 · 由 user:1 采纳", "结论 · 由 user:2 采纳"]);
    expect(new Set(labels).size).toBe(2);
  });
});

describe("批次十一 C2 · 编辑 / 删除 / 附件挂载（T-C2-FE）", () => {
  const concludedComment = {
    ...COMMENT,
    concluded: true,
    node_type: "conclusion",
    concluded_by_type: "user",
    concluded_by_id: "1",
    concluded_by_name: "张三",
  };

  it("① 编辑：改正文 → `PATCH /projects/p1/comments/cmt_1`（体 = {body}）", async () => {
    comments = [COMMENT];
    renderTab();

    fireEvent.click(await screen.findByTestId("comment-edit"));
    const input = await screen.findByTestId("comment-edit-input");
    expect(input).toHaveValue(COMMENT.body);
    fireEvent.change(input, { target: { value: "改后的正文" } });
    fireEvent.click(screen.getByTestId("comment-edit-save"));

    await waitFor(() => {
      const call = mockedRequest.mock.calls.find(
        ([path, init]) =>
          path === "/projects/p1/comments/cmt_1" &&
          (init as RequestInit | undefined)?.method === "PATCH",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
        body: "改后的正文",
      });
    });
  });

  it("② 删除（未采纳）：`DELETE /projects/p1/comments/cmt_1`", async () => {
    comments = [COMMENT];
    renderTab();

    fireEvent.click(await screen.findByTestId("comment-delete"));
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.some(
          ([path, init]) =>
            path === "/projects/p1/comments/cmt_1" &&
            (init as RequestInit | undefined)?.method === "DELETE",
        ),
      ).toBe(true),
    );
  });

  it("★★ 已采纳 ⇒ 删除【事前禁用】+ 提示用【后端同一个键】（apiErrors.PROJECT_COMMENT_CONCLUDED）", async () => {
    comments = [concludedComment];
    renderTab();

    const del = await screen.findByTestId("comment-delete");
    expect(del).toBeDisabled();
    // ★ 与 409 的 message 同源（本卡只引用键、不改 locales）。
    expect(screen.getByTestId("comment-delete-blocked")).toHaveTextContent(
      "该留言已被采纳为结论，请先取消采纳后再删除。",
    );
    // 即便强行点击也不发 DELETE（禁用是事前门 + 服务端 409 兜底）。
    fireEvent.click(del);
    await Promise.resolve();
    expect(
      mockedRequest.mock.calls.some(
        ([path, init]) =>
          path === "/projects/p1/comments/cmt_1" &&
          (init as RequestInit | undefined)?.method === "DELETE",
      ),
    ).toBe(false);
  });

  it("③ 附件挂载：暂存（POST …/attachments）→ 绑定（PATCH …/attachments/{id}，comment_id）", async () => {
    comments = [COMMENT];
    // ★ 暂存走 `requestUpload`（multipart）⇒ 它是**独立** mock，必须单独注入。
    mockedUpload.mockResolvedValue({ artifact_id: "art_1" } as never);
    mockedRequest.mockImplementation(
      async (path: string, init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        if (path === "/projects/p1/attachments" && method === "POST")
          return { artifact_id: "art_1" } as never;
        if (path.startsWith("/projects/p1/comments")) return comments as never;
        if (path === "/projects/p1/members") return [MEMBER] as never;
        return null as never;
      },
    );
    renderTab();

    const input = await screen.findByTestId("comment-attachment-input");
    const file = new File(["x"], "shot.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(
        mockedUpload.mock.calls.some(
          ([path]) => path === "/projects/p1/attachments",
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.some(
          ([path, init]) =>
            path === "/projects/p1/attachments/art_1" &&
            (init as RequestInit | undefined)?.method === "PATCH" &&
            JSON.parse(String((init as RequestInit).body)).comment_id ===
              "cmt_1",
        ),
      ).toBe(true),
    );
  });

  it("★ viewer（只读）不渲染写入口（既有门未破坏）", async () => {
    comments = [COMMENT];
    mockedRequest.mockImplementation(async (path: string) => {
      if (path.startsWith("/projects/p1/comments")) return comments as never;
      if (path === "/projects/p1/members") return [] as never; // 非成员 ⇒ 只读
      return null as never;
    });
    renderTab();

    await screen.findByTestId("feed-item");
    expect(screen.queryByTestId("comment-edit")).toBeNull();
    expect(screen.queryByTestId("comment-delete")).toBeNull();
    expect(screen.queryByTestId("comment-attach")).toBeNull();
  });
});

describe("批次十二 F · 与我相关 / 按人筛选 / 显式提及（T-F-FE）", () => {
  const TWO_MEMBERS = [
    { ...MEMBER, subject_id: "u1", user_id: 1, name: "张三" },
    {
      ...MEMBER,
      subject_type: "agent",
      subject_id: "agt_9",
      user_id: null,
      name: "小助手",
      role: "member",
    },
  ];

  const feedPaths = () =>
    mockedRequest.mock.calls
      .map(([path]) => String(path))
      .filter((path) => path.startsWith("/projects/p1/comments"));

  it("① 「与我相关」= 筛选参数 `relevance=me`（P3：不是新视图）", async () => {
    comments = [];
    renderTab();
    fireEvent.click(await screen.findByTestId("feed-relevance-toggle"));

    await waitFor(() =>
      expect(feedPaths().some((path) => path.includes("relevance=me"))).toBe(
        true,
      ),
    );
  });

  it("② 按人筛选：`author_id` + `author_type` **成对**下发（候选 = 项目成员）", async () => {
    comments = [];
    mockedRequest.mockImplementation(async (path: string) => {
      if (path.startsWith("/projects/p1/comments")) return comments as never;
      if (path === "/projects/p1/members") return TWO_MEMBERS as never;
      return null as never;
    });
    renderTab();

    const select = await screen.findByTestId("feed-author-filter");
    // ★ §20.22：先断言候选集**非空**，再遍历/选择它的成员。
    expect(within(select).getAllByRole("option").length).toBeGreaterThan(1);
    expect(
      within(select).getByTestId("feed-author-option-agt_9"),
    ).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "agent:agt_9" } });
    await waitFor(() =>
      expect(
        feedPaths().some(
          (path) =>
            path.includes("author_id=agt_9") &&
            path.includes("author_type=agent"),
        ),
      ).toBe(true),
    );
  });

  it("★ P5：两种空态【分别】文案（与我相关空 ≠ 筛选导致空）", async () => {
    comments = [];
    renderTab();

    // (a) 与我相关 + 空 ⇒ 专属空态
    fireEvent.click(await screen.findByTestId("feed-relevance-toggle"));
    expect(await screen.findByTestId("feed-empty-relevance")).toHaveTextContent(
      "没有与你相关的留言",
    );
    expect(screen.queryByTestId("feed-empty-filtered")).toBeNull();
    expect(screen.queryByTestId("feed-empty")).toBeNull();

    // (b) 关闭后回到中性空态
    fireEvent.click(screen.getByTestId("feed-relevance-toggle"));
    expect(await screen.findByTestId("feed-empty")).toHaveTextContent(
      "暂无留言",
    );
  });

  it("③ 提及：**显式点选**产生（无文本解析）⇒ POST 体带 `mentions:[{type,id}]`", async () => {
    comments = [];
    mockedRequest.mockImplementation(
      async (path: string, init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        if (path === "/projects/p1/comments" && method === "POST")
          return COMMENT as never;
        if (path.startsWith("/projects/p1/comments")) return comments as never;
        if (path === "/projects/p1/members") return TWO_MEMBERS as never;
        return null as never;
      },
    );
    renderTab();

    // ⑥：候选集非空再点选。
    const picker = await screen.findByTestId("feed-mention-picker");
    expect(within(picker).getAllByRole("option").length).toBeGreaterThan(1);
    fireEvent.change(picker, { target: { value: "agent:agt_9" } });
    expect(
      await screen.findByTestId("feed-mention-chip-agt_9"),
    ).toBeInTheDocument();

    const composer = screen.getByTestId("feed-composer");
    fireEvent.change(within(composer).getByPlaceholderText("写点什么…"), {
      target: { value: "请看一下" },
    });
    fireEvent.click(within(composer).getByText("发布"));

    await waitFor(() => {
      const post = mockedRequest.mock.calls.find(
        ([path, init]) =>
          path === "/projects/p1/comments" &&
          (init as RequestInit | undefined)?.method === "POST",
      );
      expect(post).toBeTruthy();
      expect(JSON.parse(String((post?.[1] as RequestInit).body))).toEqual({
        body: "请看一下",
        mentions: [{ type: "agent", id: "agt_9" }],
      });
    });
  });

  it("★ `[]` 与「未动过」**两存**：显式清空 ⇒ 体带 `mentions: []`；未动过 ⇒ **无该键**（NULL）", async () => {
    comments = [];
    mockedRequest.mockImplementation(
      async (path: string, init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        if (path === "/projects/p1/comments" && method === "POST")
          return COMMENT as never;
        if (path.startsWith("/projects/p1/comments")) return comments as never;
        if (path === "/projects/p1/members") return TWO_MEMBERS as never;
        return null as never;
      },
    );
    renderTab();

    const composer = await screen.findByTestId("feed-composer");
    const body = () => {
      const post = mockedRequest.mock.calls
        .filter(
          ([path, init]) =>
            path === "/projects/p1/comments" &&
            (init as RequestInit | undefined)?.method === "POST",
        )
        .pop();
      return JSON.parse(String((post?.[1] as RequestInit).body));
    };

    // (a) 未动过提及 ⇒ 不带该键（NULL 事实）
    fireEvent.change(within(composer).getByPlaceholderText("写点什么…"), {
      target: { value: "A" },
    });
    fireEvent.click(within(composer).getByText("发布"));
    await waitFor(() => expect(body().body).toBe("A"));
    expect("mentions" in body()).toBe(false);

    // (b) 显式清空 ⇒ `[]`（显式"没 @ 任何人"事实）
    const picker = screen.getByTestId("feed-mention-picker");
    fireEvent.change(picker, { target: { value: "user:u1" } });
    fireEvent.click(await screen.findByTestId("feed-mentions-clear"));
    fireEvent.change(within(composer).getByPlaceholderText("写点什么…"), {
      target: { value: "B" },
    });
    fireEvent.click(within(composer).getByText("发布"));
    await waitFor(() => expect(body().body).toBe("B"));
    expect(body().mentions).toEqual([]);
  });
});
