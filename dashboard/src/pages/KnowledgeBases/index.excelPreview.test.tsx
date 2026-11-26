import type { ReactNode } from "react";
import { App } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
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
vi.mock("../../components/DocumentPreviewCore", async () => {
  const { useEffect } = await import("react");
  return {
    default: function PreviewMock({
      fetchBlob,
    }: {
      fetchBlob: () => Promise<Blob>;
    }) {
      useEffect(() => {
        void fetchBlob().catch(() => {});
      }, [fetchBlob]);
      return null;
    },
  };
});
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
    fetchDocumentFile: vi.fn(),
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

it("refreshes an Excel preview once indexing finishes", async () => {
  documents = [
    {
      id: "excel-1",
      kb_id: base.id,
      filename: "report.xlsx",
      path: "report.xlsx",
      is_dir: false,
      content_type:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      byte_size: 100,
      status: "processing",
      error_message: "",
      chunk_count: 0,
      created_at: 0,
      updated_at: 0,
      has_original: true,
    } as KnowledgeDocument,
  ];
  vi.mocked(knowledgeBasesApi.fetchDocumentFile).mockRejectedValueOnce(
    new Error("not ready"),
  );
  render(
    <MemoryRouter>
      <KnowledgeBasesPage />
    </MemoryRouter>,
  );
  fireEvent.click(
    await screen.findByLabelText("knowledgeBases.previewDocument"),
  );
  await waitFor(() =>
    expect(knowledgeBasesApi.fetchDocumentFile).toHaveBeenCalledTimes(1),
  );
  vi.mocked(knowledgeBasesApi.fetchDocumentFile).mockResolvedValue(
    new Blob(["recalculated"]),
  );
  documents = [{ ...documents[0], status: "ready", chunk_count: 1 }];
  await waitFor(
    () => expect(knowledgeBasesApi.fetchDocumentFile).toHaveBeenCalledTimes(2),
    { timeout: 5000 },
  );
  expect(knowledgeBasesApi.fetchDocumentFile).toHaveBeenLastCalledWith(
    base.id,
    "excel-1",
    "inline",
    undefined,
    undefined,
  );
  expect(
    screen.getAllByLabelText("knowledgeBases.previewDocument"),
  ).toHaveLength(1);
}, 10000);
