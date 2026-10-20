import type { ReactNode } from "react";
import { App } from "antd";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  knowledgeBasesApi,
  type KnowledgeBase,
  type KnowledgeDocument,
} from "../../api/modules/knowledgeBases";
import KnowledgeBasesPage from ".";

vi.mock("react-i18next", () => {
  const t = (key: string, options?: { name?: string }) =>
    options?.name ? `${key} ${options.name}` : key;
  return { useTranslation: () => ({ t }) };
});
vi.mock("../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({
    id: 7,
    role: "member",
    permissions: ["knowledge_bases"],
  }),
}));
vi.mock("../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "Asia/Shanghai",
}));
vi.mock("../../layouts/PageShell", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("../../components/DocumentPreviewCore", () => ({
  default: () => null,
}));
vi.mock("../../components/Markdown", () => ({ default: () => null }));
vi.mock("../../components/StreamSetupGuide/StreamSetupGuide", () => ({
  default: () => null,
}));
vi.mock("../../api/modules/knowledgeBases", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../api/modules/knowledgeBases")
  >()),
  knowledgeBasesApi: {
    list: vi.fn(),
    get: vi.fn(),
    listDocuments: vi.fn(),
    getCapability: vi.fn(),
    uploadDocument: vi.fn(),
  },
}));

const notice = { error: vi.fn(), warning: vi.fn(), success: vi.fn() };
let base: KnowledgeBase;
let documents: KnowledgeDocument[];
let maxBytes: number;
let ocrUsable: boolean;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  maxBytes = 100;
  ocrUsable = false;
  documents = [];
  base = {
    id: "kb-add",
    owner_user_id: 7,
    name: "Upload target",
    description: "",
    default_open: false,
    shared: true,
    icon_name: "",
    embedding_model: "test",
    embedding_dim: 3,
    doc_count: 0,
    max_documents: 100,
    created_at: 0,
    updated_at: 0,
  };
  vi.spyOn(App, "useApp").mockReturnValue({
    message: notice,
    modal: {},
  } as unknown as ReturnType<typeof App.useApp>);
  vi.mocked(knowledgeBasesApi.list).mockImplementation(async () => [base]);
  vi.mocked(knowledgeBasesApi.get).mockImplementation(async () => base);
  vi.mocked(knowledgeBasesApi.listDocuments).mockImplementation(
    async () => documents,
  );
  vi.mocked(knowledgeBasesApi.getCapability).mockImplementation(async () => ({
    usable: true,
    feature_enabled: true,
    prerequisites_ok: true,
    backend: "onnx",
    selected_model: "test",
    provider_id: "",
    checks: {
      deps_available: true,
      model_selected: true,
      model_downloaded: true,
      provider_ready: true,
    },
    ocr: {
      enabled: ocrUsable,
      usable: ocrUsable,
      prerequisites_ok: ocrUsable,
      backend: "onnx",
      model: "test",
      provider_id: "",
      checks: { deps_available: true, provider_ready: true },
    },
    limits: {
      max_bases_per_owner: 10,
      max_docs_per_kb: 100,
      max_document_bytes: maxBytes,
    },
  }));
  vi.mocked(knowledgeBasesApi.uploadDocument).mockResolvedValue(
    {} as KnowledgeDocument,
  );
});

function folderFile(path: string, content = "original\r\n") {
  const file = new File([content], path.split("/").at(-1)!, {
    type: "text/plain",
  });
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

async function openPage() {
  const view = render(
    <MemoryRouter>
      <KnowledgeBasesPage />
    </MemoryRouter>,
  );
  await screen.findByLabelText("knowledgeBases.uploadFolder");
  return view;
}

function selectFolder(files: File[]) {
  const input = screen.getByLabelText("knowledgeBases.uploadFolder");
  fireEvent.change(input, { target: { files } });
  return input;
}

function selectedBaseName() {
  const active = document.querySelector('[class*="_active_"]');
  const name = active?.querySelector('[class*="_listNameText_"]');
  if (!name?.textContent) throw new Error("no selected knowledge base");
  return name.textContent;
}

describe("knowledge-base folder upload", () => {
  it("opens a directory picker and preserves root, nested paths, same names and original files", async () => {
    await openPage();
    const input = screen.getByLabelText("knowledgeBases.uploadFolder");
    expect(input).toHaveAttribute("webkitdirectory");
    const click = vi.spyOn(input, "click");
    fireEvent.click(
      screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
    );
    expect(click).toHaveBeenCalledOnce();
    const files = [
      folderFile("资料/一组/说明.md"),
      folderFile("资料/二组/说明.md"),
    ];
    selectFolder(files);
    await waitFor(() =>
      expect(notice.success).toHaveBeenCalledWith("knowledgeBases.uploaded"),
    );
    expect(
      vi
        .mocked(knowledgeBasesApi.uploadDocument)
        .mock.calls.map((call) => call.slice(0, 3)),
    ).toEqual([
      ["kb-add", files[0], "资料/一组/说明.md"],
      ["kb-add", files[1], "资料/二组/说明.md"],
    ]);
    expect(input).toHaveValue("");
  });

  it("normalizes a trailing slash on the current folder before upload", async () => {
    documents = [
      {
        id: "folder",
        filename: "现有目录",
        path: "./现有目录/",
        is_dir: true,
      } as KnowledgeDocument,
    ];
    await openPage();
    fireEvent.click(await screen.findByRole("button", { name: /现有目录/ }));
    const file = folderFile("资料/子目录/a.txt");
    selectFolder([file]);
    await waitFor(() =>
      expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledWith(
        "kb-add",
        file,
        "现有目录/资料/子目录/a.txt",
        expect.any(Function),
      ),
    );
  });

  it("uploads into the currently opened knowledge-base folder", async () => {
    documents = [
      {
        id: "folder",
        filename: "现有目录",
        path: "现有目录",
        is_dir: true,
      } as KnowledgeDocument,
    ];
    await openPage();
    fireEvent.click(await screen.findByRole("button", { name: /现有目录/ }));
    const file = folderFile("资料/子目录/a.txt");
    selectFolder([file]);
    await waitFor(() =>
      expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledWith(
        "kb-add",
        file,
        "现有目录/资料/子目录/a.txt",
        expect.any(Function),
      ),
    );
  });

  it("keeps ordinary multi-file uploads at the current level", async () => {
    const { container } = await openPage();
    const file = new File(["plain"], "plain.txt");
    fireEvent.change(
      container.querySelector('input[type="file"]:not([webkitdirectory])')!,
      { target: { files: [file] } },
    );
    await waitFor(() =>
      expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledWith(
        "kb-add",
        file,
        "plain.txt",
        expect.any(Function),
      ),
    );
  });

  it("skips unsupported types and images when OCR is unavailable", async () => {
    await openPage();
    const good = folderFile("资料/a.md");
    selectFolder([folderFile("资料/a.exe"), folderFile("资料/a.png"), good]);
    await waitFor(() => expect(notice.success).toHaveBeenCalled());
    expect(notice.warning).toHaveBeenCalledWith(
      "knowledgeBases.dropUploadUnsupported",
    );
    expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledOnce();
    expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledWith(
      "kb-add",
      good,
      "资料/a.md",
      expect.any(Function),
    );
  });

  it("accepts images when OCR is usable", async () => {
    ocrUsable = true;
    await openPage();
    const file = folderFile("扫描/图.png");
    selectFolder([file]);
    await waitFor(() =>
      expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledWith(
        "kb-add",
        file,
        "扫描/图.png",
        expect.any(Function),
      ),
    );
  });

  it("allows selecting the same folder again after all files were skipped", async () => {
    await openPage();
    const file = folderFile("资料/a.exe");
    const input = selectFolder([file]);
    expect(input).toHaveValue("");
    selectFolder([file]);
    expect(notice.warning).toHaveBeenCalledTimes(2);
    expect(knowledgeBasesApi.uploadDocument).not.toHaveBeenCalled();
  });

  it("rejects parent traversal before sending a file", async () => {
    await openPage();
    selectFolder([folderFile("资料/../secret.txt")]);
    await waitFor(() => expect(notice.error).toHaveBeenCalled());
    expect(knowledgeBasesApi.uploadDocument).not.toHaveBeenCalled();
  });

  it("rejects oversized batches before uploading and allows a new selection", async () => {
    maxBytes = 3;
    await openPage();
    selectFolder([folderFile("资料/large.txt", "four")]);
    expect(notice.error).toHaveBeenCalledWith(
      "knowledgeBases.documentTooLarge",
    );
    expect(knowledgeBasesApi.uploadDocument).not.toHaveBeenCalled();
    selectFolder([folderFile("资料/small.txt", "ok")]);
    await waitFor(() =>
      expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledOnce(),
    );
  });

  it("applies the remaining document cap to a folder batch", async () => {
    base.max_documents = 1;
    await openPage();
    selectFolder([folderFile("资料/a.txt"), folderFile("资料/b.txt")]);
    await waitFor(() => expect(notice.success).toHaveBeenCalled());
    expect(notice.warning).toHaveBeenCalledWith(
      "knowledgeBases.documentLimitReached",
    );
    expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledOnce();
  });

  it("disables folder upload at the document cap", async () => {
    base.max_documents = 1;
    documents = [
      {
        id: "file",
        path: "a.txt",
        filename: "a.txt",
        status: "ready",
      } as KnowledgeDocument,
    ];
    await openPage();
    expect(
      screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
    ).toBeDisabled();
    selectFolder([folderFile("资料/b.txt")]);
    expect(knowledgeBasesApi.uploadDocument).not.toHaveBeenCalled();
  });

  it("hides the action and rejects changes for a read-only employee", async () => {
    base.owner_user_id = 99;
    await openPage();
    expect(
      screen.queryByRole("button", { name: "knowledgeBases.uploadFolder" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("knowledgeBases.uploadFolder")).toBeDisabled();
    selectFolder([folderFile("资料/a.txt")]);
    expect(knowledgeBasesApi.uploadDocument).not.toHaveBeenCalled();
  });

  it("shows the nested path and progress and blocks a second batch while uploading", async () => {
    let finish!: () => void;
    vi.mocked(knowledgeBasesApi.uploadDocument).mockImplementation(
      (_kb, _file, _path, progress) => {
        progress?.(42);
        return new Promise((resolve) => {
          finish = () => resolve({} as KnowledgeDocument);
        });
      },
    );
    await openPage();
    selectFolder([folderFile("资料/层级/a.txt")]);
    await waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute(
        "aria-valuenow",
        "42",
      ),
    );
    expect(
      screen.getByText("knowledgeBases.uploading 资料/层级/a.txt"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
    ).toBeDisabled();
    selectFolder([folderFile("资料/b.txt")]);
    expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledOnce();
    await act(async () => finish());
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
      ).toBeEnabled(),
    );
  });

  it("hides folder upload progress on another knowledge base and does not jump back", async () => {
    const other: KnowledgeBase = {
      ...base,
      id: "kb-other",
      name: "Other base",
    };
    vi.mocked(knowledgeBasesApi.list).mockImplementation(async () => [
      base,
      other,
    ]);
    vi.mocked(knowledgeBasesApi.get).mockImplementation(async (id) =>
      id === other.id ? other : base,
    );
    let finish!: () => void;
    vi.mocked(knowledgeBasesApi.uploadDocument).mockImplementation(
      (_kb, _file, _path, progress) => {
        progress?.(42);
        return new Promise((resolve) => {
          finish = () => resolve({} as KnowledgeDocument);
        });
      },
    );
    await openPage();
    const file = folderFile("资料/层级/a.txt");
    selectFolder([file]);
    await waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute(
        "aria-valuenow",
        "42",
      ),
    );
    expect(selectedBaseName()).toBe("Upload target");
    fireEvent.click(screen.getByText("Other base"));
    await waitFor(() => expect(selectedBaseName()).toBe("Other base"));
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
    ).toBeDisabled();
    const getsBeforeFinish = vi.mocked(knowledgeBasesApi.get).mock.calls.length;
    await act(async () => finish());
    await waitFor(() =>
      expect(notice.success).toHaveBeenCalledWith("knowledgeBases.uploaded"),
    );
    expect(selectedBaseName()).toBe("Other base");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(vi.mocked(knowledgeBasesApi.get).mock.calls.length).toBe(
      getsBeforeFinish,
    );
    expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledWith(
      "kb-add",
      file,
      "资料/层级/a.txt",
      expect.any(Function),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
      ).toBeEnabled(),
    );
  });

  it("re-enables upload when the post-upload refresh fails", async () => {
    let listed = 0;
    vi.mocked(knowledgeBasesApi.listDocuments).mockImplementation(async () => {
      listed += 1;
      if (listed > 1) throw new Error("refresh failed");
      return documents;
    });
    vi.mocked(knowledgeBasesApi.list).mockImplementation(async () => {
      if (listed > 1) throw new Error("refresh failed");
      return [base];
    });
    await openPage();
    selectFolder([folderFile("资料/a.txt")]);
    await waitFor(() =>
      expect(notice.success).toHaveBeenCalledWith("knowledgeBases.uploaded"),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
      ).toBeEnabled(),
    );
    expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledOnce();
  });

  it("stops on a rejected file and refreshes successful uploads", async () => {
    vi.mocked(knowledgeBasesApi.uploadDocument)
      .mockResolvedValueOnce({} as KnowledgeDocument)
      .mockRejectedValueOnce(new Error("rejected"));
    await openPage();
    selectFolder([
      folderFile("资料/a.txt"),
      folderFile("资料/b.txt"),
      folderFile("资料/c.txt"),
    ]);
    await waitFor(() => expect(notice.error).toHaveBeenCalledWith("rejected"));
    await waitFor(() =>
      expect(knowledgeBasesApi.listDocuments).toHaveBeenCalledTimes(3),
    );
    expect(knowledgeBasesApi.list).toHaveBeenCalledTimes(2);
    expect(knowledgeBasesApi.uploadDocument).toHaveBeenCalledTimes(2);
    expect(notice.success).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "knowledgeBases.uploadFolder" }),
    ).toBeEnabled();
  });
});
