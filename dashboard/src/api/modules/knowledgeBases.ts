import { request, requestUpload } from "../request";

export interface KnowledgeLimits {
  max_bases_per_owner: number;
  max_docs_per_kb: number;
  max_document_bytes: number;
}

export interface KnowledgeCapability {
  feature_enabled: boolean;
  backend: "onnx" | "remote";
  selected_model: string;
  provider_id: string;
  prerequisites_ok: boolean;
  usable: boolean;
  checks: {
    model_selected: boolean;
    model_downloaded: boolean;
    deps_available: boolean;
    provider_ready: boolean;
  };
  limits?: KnowledgeLimits;
}

export interface KnowledgeBase {
  id: string;
  knowledge_base_id?: string;
  pk?: number;
  owner_user_id: number;
  owner_username?: string | null;
  owner_display_name?: string | null;
  name: string;
  description: string;
  default_open: boolean;
  shared: boolean;
  icon_name: string;
  embedding_model: string;
  embedding_dim: number;
  doc_count: number;
  max_documents: number;
  created_at: number;
  updated_at: number;
}

export interface KnowledgeDocument {
  id: string;
  document_id?: string;
  kb_id: string;
  path?: string;
  filename: string;
  is_dir?: boolean;
  content_type: string;
  byte_size: number;
  content_hash: string;
  status: "pending" | "processing" | "ready" | "failed";
  error_message: string;
  chunk_count: number;
  created_at: number;
  updated_at: number;
}

export interface KnowledgeOnnxModel {
  id: string;
  name: string;
  downloaded: boolean;
  recommended?: boolean;
  size_gb?: number | null;
}

export interface KnowledgeEmbeddingOptions {
  onnx: KnowledgeOnnxModel[];
  remote: {
    provider_id: string;
    provider_name: string;
    models: { id: string; name: string }[];
  }[];
}

export interface KnowledgeOnnxDownloadState {
  status: "idle" | "downloading" | "loading" | "done" | "failed";
  progress: number;
  error?: string | null;
  model_name: string;
  task_id?: string;
}

export const DEFAULT_KNOWLEDGE_LIMITS: KnowledgeLimits = {
  max_bases_per_owner: 20,
  max_docs_per_kb: 100,
  max_document_bytes: 100 * 1024 * 1024,
};

export const knowledgeBasesApi = {
  getCapability: () =>
    request<KnowledgeCapability>("/knowledge-bases/capability"),

  setFeature: (body: {
    enabled: boolean;
    backend?: "onnx" | "remote";
    model?: string;
    provider_id?: string;
  }) =>
    request<KnowledgeCapability>("/knowledge-bases/feature", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  list: () => request<KnowledgeBase[]>("/knowledge-bases"),
  getEmbeddingOptions: (opts?: { allOnnx?: boolean }) =>
    request<KnowledgeEmbeddingOptions>(
      opts?.allOnnx
        ? "/knowledge-bases/embedding-options?all_onnx=true"
        : "/knowledge-bases/embedding-options",
    ),

  downloadOnnx: (model: string) =>
    request<KnowledgeOnnxDownloadState>("/knowledge-bases/onnx-download", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),

  getOnnxDownloadStatus: () =>
    request<KnowledgeOnnxDownloadState>(
      "/knowledge-bases/onnx-download-status",
    ),

  testOnnx: (model: string) =>
    request<{
      ok: boolean;
      latency_ms?: number | null;
      dim?: number | null;
      error?: string | null;
    }>("/knowledge-bases/onnx-test", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),

  activateOnnx: (model: string) =>
    request<{ enabled: boolean; model: string; ready: boolean }>(
      "/knowledge-bases/onnx-activate",
      {
        method: "POST",
        body: JSON.stringify({ model }),
      },
    ),

  get: (id: string) => request<KnowledgeBase>(`/knowledge-bases/${id}`),

  create: (body: {
    name: string;
    description?: string;
    default_open?: boolean;
    shared?: boolean;
    icon_name?: string;
    max_documents?: number;
  }) =>
    request<KnowledgeBase>("/knowledge-bases", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  update: (
    id: string,
    body: {
      name?: string;
      description?: string;
      default_open?: boolean;
      shared?: boolean;
      icon_name?: string;
      max_documents?: number;
    },
  ) =>
    request<KnowledgeBase>(`/knowledge-bases/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (id: string) =>
    request<void>(`/knowledge-bases/${id}`, { method: "DELETE" }),

  listDocuments: (id: string, prefix?: string) =>
    request<KnowledgeDocument[]>(
      prefix
        ? `/knowledge-bases/${id}/documents?prefix=${encodeURIComponent(
            prefix,
          )}`
        : `/knowledge-bases/${id}/documents`,
    ),

  createFolder: (id: string, path: string) =>
    request<KnowledgeDocument>(`/knowledge-bases/${id}/folders`, {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  createTextDocument: (
    id: string,
    body: {
      name: string;
      format: "md" | "txt";
      content?: string;
      path?: string;
    },
  ) =>
    request<KnowledgeDocument>(`/knowledge-bases/${id}/documents/text`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getTextDocument: (id: string, documentId: string) =>
    request<{
      id: string;
      filename: string;
      content_type: string;
      text: string;
    }>(`/knowledge-bases/${id}/documents/${documentId}/content`),

  updateTextDocument: (id: string, documentId: string, content: string) =>
    request<KnowledgeDocument>(
      `/knowledge-bases/${id}/documents/${documentId}/content`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),

  uploadDocument: (id: string, file: File, relativePath?: string) => {
    const body = new FormData();
    body.append("upload", file);
    if (relativePath) body.append("path", relativePath);
    return requestUpload<KnowledgeDocument>(
      `/knowledge-bases/${id}/documents`,
      body,
      { method: "POST" },
    );
  },

  deleteDocument: (id: string, documentId: string) =>
    request<void>(`/knowledge-bases/${id}/documents/${documentId}`, {
      method: "DELETE",
    }),

  reindexDocument: (id: string, documentId: string) =>
    request<KnowledgeDocument>(
      `/knowledge-bases/${id}/documents/${documentId}/reindex`,
      { method: "POST" },
    ),

  previewDocument: (id: string, documentId: string) =>
    request<{ id: string; filename: string; text: string }>(
      `/knowledge-bases/${id}/documents/${documentId}/preview`,
    ),

  reindex: (id: string) =>
    request<{ enqueued: number }>(`/knowledge-bases/${id}/reindex`, {
      method: "POST",
    }),

  renameDocument: (id: string, documentId: string, newName: string) =>
    request<KnowledgeDocument>(
      `/knowledge-bases/${id}/documents/${documentId}/rename`,
      {
        method: "POST",
        body: JSON.stringify({ new_name: newName }),
      },
    ),
};
