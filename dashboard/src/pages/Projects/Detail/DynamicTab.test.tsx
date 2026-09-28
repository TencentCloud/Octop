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

import { request } from "../../../api/request";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import DynamicTab from "./DynamicTab";

const mockedRequest = vi.mocked(request);

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
    if (path === "/projects/p1/comments" && method === "GET")
      return comments as never;
    if (path === "/projects/p1/comments" && method === "POST")
      return COMMENT as never;
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
