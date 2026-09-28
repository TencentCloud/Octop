import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Only the transport is mocked: the tab must go through the shared
// ``knowledgeBasesApi`` wrapper, so asserting on ``request`` proves the real
// path and proves that the empty branch issues nothing at all.
// 仓内既有惯例（`DocumentPreviewCore.pdfSkeleton.test.tsx` 同款）：真实挂载
// `DocumentPreviewCore`，只把 pdfjs 渲染器打桩 —— jsdom 无 `DOMMatrix`。
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

// ``useServerTimezone`` fetches the server timezone on its own; pinning it keeps
// the request count attributable to the knowledge-base read alone.
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
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
import AssetsTab from "./AssetsTab";
import DynamicTab from "./DynamicTab";

const mockedRequest = vi.mocked(request);
const mockedBlob = vi.mocked(requestBlob);

const KB = {
  id: "kb1",
  owner_user_id: 1,
  name: "Project Alpha KB",
  description: "",
  default_open: false,
  shared: false,
  icon_name: "",
  embedding_model: "m",
  embedding_dim: 768,
  doc_count: 7,
  max_documents: 100,
  created_at: 1700000000,
  updated_at: 1700000100,
};

function renderTab(node: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={["/projects/p1"]}>{node}</MemoryRouter>,
  );
}

/** 文档夹具（`is_dir` + `path` 扁平模型）。 */
const DOCS = [
  { id: "d_dir", kb_id: "kb1", path: "手册", filename: "手册", is_dir: true },
  {
    id: "d_file",
    kb_id: "kb1",
    path: "readme.txt",
    filename: "readme.txt",
    is_dir: false,
  },
];

beforeEach(() => {
  mockedRequest.mockReset();
  mockedRequest.mockImplementation(async (path: string) => {
    if (path.startsWith("/knowledge-bases/kb1/documents")) return DOCS as never;
    if (path.startsWith("/knowledge-bases/kb")) return KB as never;
    return null as never;
  });
  mockedBlob.mockReset();
  mockedBlob.mockResolvedValue(new Blob(["x"]) as never);
  // jsdom 无 object URL API（真实浏览器有）：文件级注入，避免组件 cleanup 期缺失。
  URL.createObjectURL = vi.fn(() => "blob:asset") as never;
  URL.revokeObjectURL = vi.fn() as never;
});

describe("assets tab — data source is projects.kb_id (PLAN §19.3)", () => {
  it("renders the empty branch and issues no request when kb_id is null", async () => {
    renderTab(<AssetsTab kbId={null} />);

    // ★ Assert the branch that was taken, not merely that nothing threw: the
    //   empty-state marker can only exist on the no-kb path.
    expect(
      await screen.findByTestId("project-assets-empty"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("project-assets")).not.toBeInTheDocument();
    expect(screen.getByText("projects.assetEmpty")).toBeInTheDocument();
    expect(screen.getByText("projects.assetBind")).toBeInTheDocument();

    // A null kb_id is a supported state, so it must not read anything.
    await waitFor(() => expect(mockedRequest).not.toHaveBeenCalled());
  });

  it("loads the bound knowledge base and shows its name, count and updated time", async () => {
    // documents 读环与 kb 读环**返回不同形状** ⇒ 按端点注入（断言强度不变）。
    mockedRequest.mockImplementation(
      async (path: string) =>
        (path.startsWith("/knowledge-bases/kb1/documents") ? [] : KB) as never,
    );
    renderTab(<AssetsTab kbId="kb1" />);

    expect(await screen.findByTestId("project-assets")).toBeInTheDocument();
    expect(
      screen.queryByTestId("project-assets-empty"),
    ).not.toBeInTheDocument();

    // ★ 作用域收敛（批次七）：现在同一屏还读 documents ⇒ 计数限定在 **kb 端点**
    //   （强度不变：仍要求该端点**恰好一次**）。
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.filter(([p]) => p === "/knowledge-bases/kb1"),
      ).toHaveLength(1),
    );
    // ★ 同源补一条（批次七返工 · 审查员突变 C 的残留盲区）：**documents 端点同样恰好一次**。
    //   收窄成端点作用域后，「重复请求 documents」原先无人看 ⇒ 这里补齐，强度与上一条对齐。
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.filter(
          ([p]) => p === "/knowledge-bases/kb1/documents",
        ),
      ).toHaveLength(1),
    );

    expect(await screen.findByText("Project Alpha KB")).toBeInTheDocument();
    // The count is rendered through the frozen key with its placeholder filled.
    expect(screen.getByText("projects.assetDocCount")).toBeInTheDocument();
    expect(screen.getByText("projects.assetOpen")).toBeInTheDocument();
  });

  it("re-reads the knowledge base when kb_id changes", async () => {
    mockedRequest.mockImplementation(
      async (path: string) => (path.includes("/documents") ? [] : KB) as never,
    );
    const { rerender } = renderTab(<AssetsTab kbId="kb1" />);
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.filter(([p]) => p === "/knowledge-bases/kb1"),
      ).toHaveLength(1),
    );

    rerender(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <AssetsTab kbId="kb2" />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.filter(([p]) => p === "/knowledge-bases/kb2"),
      ).toHaveLength(1),
    );
  });
});

describe("activity tab — a placeholder, not the feed (PLAN §4.1)", () => {
  it("renders the placeholder copy and never touches the network", async () => {
    renderTab(<DynamicTab />);

    expect(await screen.findByTestId("project-dynamic")).toBeInTheDocument();
    expect(screen.getByText("projects.dynamicPlaceholder")).toBeInTheDocument();
    expect(screen.getByText("projects.dynamicComingSoon")).toBeInTheDocument();

    // ★ The hard part of "this is only a placeholder": it must not fetch a feed.
    //   The feed belongs to the next batch, so any call here would be scope
    //   leaking into this one.
    await waitFor(() => expect(mockedRequest).not.toHaveBeenCalled());
  });
});

describe("批次七 · 只读浏览：树 / 前缀 / 预览 / 回退（门三）", () => {
  it("AC-B-1：根层渲染紧凑树（目录在前），点目录用【同一端点 + prefix】进入", async () => {
    renderTab(<AssetsTab kbId="kb1" />);

    const tree = await screen.findByTestId("asset-tree");
    expect(within(tree).getByTestId("asset-dir-手册")).toBeInTheDocument();
    expect(within(tree).getByTestId("asset-file-d_file")).toBeInTheDocument();
    // 目录在前：第一行是目录。
    expect(tree.querySelectorAll("li")[0].textContent).toContain("手册");

    fireEvent.click(within(tree).getByTestId("asset-dir-手册"));

    // ★ 同一端点 + prefix（不新增端点）。
    await waitFor(() => {
      expect(
        mockedRequest.mock.calls.some(([p]) =>
          p.startsWith("/knowledge-bases/kb1/documents?prefix="),
        ),
      ).toBe(true);
    });
    expect(
      mockedRequest.mock.calls.filter(([p]) => p.includes("documents"))[0][0],
    ).toBe("/knowledge-bases/kb1/documents");
    // 面包屑出现，点根回上一层。
    expect(
      await screen.findByTestId("asset-tree-crumb-手册"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("asset-tree-root"));
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.filter(
          ([p]) => p === "/knowledge-bases/kb1/documents",
        ).length,
      ).toBeGreaterThan(1),
    );
  });

  it("AC-C-1：选中 pdf → 挂载同一个 DocumentPreviewCore（asset-preview，真实组件）", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path.startsWith("/knowledge-bases/kb1/documents"))
        return [
          {
            id: "d_pdf",
            kb_id: "kb1",
            path: "a.pdf",
            filename: "a.pdf",
            is_dir: false,
          },
        ] as never;
      return KB as never;
    });
    renderTab(<AssetsTab kbId="kb1" />);

    fireEvent.click(await screen.findByTestId("asset-file-d_pdf"));
    expect(await screen.findByTestId("asset-preview")).toBeInTheDocument();
  });

  it("AC-C-1 回退：**真·未识别类型** → asset-preview-unsupported + 下载（既有 file 端点）", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      if (path.startsWith("/knowledge-bases/kb1/documents"))
        return [
          {
            id: "d_txt",
            kb_id: "kb1",
            path: "bundle.zip",
            filename: "bundle.zip",
            is_dir: false,
          },
        ] as never;
      return KB as never;
    });
    renderTab(<AssetsTab kbId="kb1" />);

    fireEvent.click(await screen.findByTestId("asset-file-d_txt"));
    const fallback = await screen.findByTestId("asset-preview-unsupported");
    expect(fallback).toBeInTheDocument();
    expect(screen.queryByTestId("asset-preview")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("asset-download-unsupported"));
    await waitFor(() =>
      expect(
        mockedBlob.mock.calls.some(
          ([path]) =>
            path ===
            "/knowledge-bases/kb1/documents/d_txt/file?disposition=attachment",
        ),
      ).toBe(true),
    );
  });

  it("⑤ KB 0 文档 → 空态文案（不报错）", async () => {
    mockedRequest.mockImplementation(
      async (path: string) =>
        (path.startsWith("/knowledge-bases/kb1/documents") ? [] : KB) as never,
    );
    renderTab(<AssetsTab kbId="kb1" />);

    expect(await screen.findByTestId("asset-tree-empty")).toBeInTheDocument();
    expect(screen.getByTestId("asset-tree-empty")).toHaveTextContent(
      "knowledgeBases.emptyDocuments",
    );
  });

  it("★ A4：kb_id=NULL 是【非错误面】（空态 + 无失败文案 + 零请求）", async () => {
    renderTab(<AssetsTab kbId={null} />);

    expect(
      await screen.findByTestId("project-assets-empty"),
    ).toBeInTheDocument();
    // 明确断言「不是错误面」：不能出现加载失败文案，也不能有错误态 testid。
    expect(screen.queryByText("projects.loadFailed")).toBeNull();
    expect(screen.queryByTestId("project-assets")).toBeNull();
  });

  it("★ 零写面（DOM 侧）：面板内没有上传/新建/重命名/删除控件", async () => {
    renderTab(<AssetsTab kbId="kb1" />);
    const panel = await screen.findByTestId("project-assets");

    expect(panel.querySelector('input[type="file"]')).toBeNull();
    for (const name of [
      "projects.assetUpload",
      "projects.assetNewFolder",
      "projects.assetRename",
      "projects.assetDelete",
    ]) {
      expect(screen.queryByText(name)).toBeNull();
    }
  });
});

describe("批次七真机修复 · 预览通道对齐顶层知识库页（活库真实形态）", () => {
  /** 活库 KB 990G35 的真实文件形态：一个 .md + 一个 .jpg。 */
  const LIVE_DOCS = [
    {
      id: "d_md",
      kb_id: "kb1",
      path: "AGENTS.md",
      filename: "AGENTS.md",
      content_type: "text/markdown",
      is_dir: false,
    },
    {
      id: "d_jpg",
      kb_id: "kb1",
      path: "shot.jpg",
      filename: "shot.jpg",
      content_type: "image/jpeg",
      is_dir: false,
    },
  ];

  it("① .md → 【文本通道】（/content 真实路径），不再报「不支持预览」", async () => {
    mockedRequest.mockImplementation(async (path: string) => {
      // ★ 文本通道路径同样以 `/documents` 开头 ⇒ 必须先判具体端点，再判列表。
      if (path.endsWith("/documents/d_md/content"))
        return {
          id: "d_md",
          filename: "AGENTS.md",
          content_type: "text/markdown",
          text: "# 操作手册\n正文",
        } as never;
      if (path.startsWith("/knowledge-bases/kb1/documents"))
        return LIVE_DOCS as never;
      return KB as never;
    });
    renderTab(<AssetsTab kbId="kb1" />);

    fireEvent.click(await screen.findByTestId("asset-file-d_md"));
    // 等真实内容渲染（文本通道是异步读）。
    expect(await screen.findByText(/# 操作手册/)).toBeInTheDocument();
    expect(screen.getByTestId("asset-preview-text")).toBeInTheDocument();
    // ★ 不得再落到「不支持」回退。
    expect(screen.queryByTestId("asset-preview-unsupported")).toBeNull();
    // ★ 真实路径 = 既有 /content 端点。
    await waitFor(() =>
      expect(
        mockedRequest.mock.calls.some(
          ([p]) => p === "/knowledge-bases/kb1/documents/d_md/content",
        ),
      ).toBe(true),
    );
  });

  it("② .jpg → 【图片通道】直接渲染（既有取原文件 inline 端点）", async () => {
    const createObjectURL = vi.fn(() => "blob:asset-image");
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL: vi.fn(),
    });
    mockedRequest.mockImplementation(
      async (path: string) =>
        (path.startsWith("/knowledge-bases/kb1/documents")
          ? LIVE_DOCS
          : KB) as never,
    );
    mockedBlob.mockResolvedValue(new Blob(["img"]) as never);
    renderTab(<AssetsTab kbId="kb1" />);

    fireEvent.click(await screen.findByTestId("asset-file-d_jpg"));
    const image = await screen.findByTestId("asset-preview-image");
    expect(image.querySelector("img")).toBeTruthy();
    expect(screen.queryByTestId("asset-preview-unsupported")).toBeNull();
    await waitFor(() =>
      expect(
        mockedBlob.mock.calls.some(
          ([path]) =>
            path ===
            "/knowledge-bases/kb1/documents/d_jpg/file?disposition=inline",
        ),
      ).toBe(true),
    );
  });
});

describe("批次七返工 · 下载入口必须在【全部预览模式】可用（L21 载体枚举 / L24 同类对齐）", () => {
  /** 四种模式各一份真实形态样本（rich=pdf · text=md · image=jpg · unsupported=zip）。 */
  const MODES: [string, string, string][] = [
    ["rich", "d_pdf", "asset-download-rich"],
    ["text", "d_md", "asset-download-text"],
    ["image", "d_jpg", "asset-download-image"],
    ["unsupported", "d_zip", "asset-download-unsupported"],
  ];

  const SAMPLES = [
    {
      id: "d_pdf",
      kb_id: "kb1",
      path: "a.pdf",
      filename: "a.pdf",
      is_dir: false,
    },
    {
      id: "d_md",
      kb_id: "kb1",
      path: "AGENTS.md",
      filename: "AGENTS.md",
      content_type: "text/markdown",
      is_dir: false,
    },
    {
      id: "d_jpg",
      kb_id: "kb1",
      path: "shot.jpg",
      filename: "shot.jpg",
      content_type: "image/jpeg",
      is_dir: false,
    },
    {
      id: "d_zip",
      kb_id: "kb1",
      path: "bundle.zip",
      filename: "bundle.zip",
      is_dir: false,
    },
  ];

  it.each(MODES)(
    "%s 模式：有下载入口，且点击走既有 attachment 端点",
    async (_mode, docId, downloadTestId) => {
      mockedRequest.mockImplementation(async (path: string) => {
        if (path.endsWith("/documents/d_md/content"))
          return {
            id: "d_md",
            filename: "AGENTS.md",
            content_type: "text/markdown",
            text: "正文",
          } as never;
        if (path.startsWith("/knowledge-bases/kb1/documents"))
          return SAMPLES as never;
        return KB as never;
      });
      mockedBlob.mockResolvedValue(new Blob(["x"]) as never);
      renderTab(<AssetsTab kbId="kb1" />);

      fireEvent.click(await screen.findByTestId(`asset-file-${docId}`));
      const download = await screen.findByTestId(downloadTestId);
      expect(download).toBeInTheDocument();

      fireEvent.click(download);
      await waitFor(() =>
        expect(
          mockedBlob.mock.calls.some(
            ([path]) =>
              path ===
              `/knowledge-bases/kb1/documents/${docId}/file?disposition=attachment`,
          ),
        ).toBe(true),
      );
    },
  );
});
