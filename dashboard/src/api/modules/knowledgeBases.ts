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
  created_at: number;
  updated_at: number;
}

export interface KnowledgeDocument {
  id: string;
  kb_id: string;
  filename: string;
  content_type: string;
  byte_size: number;
  content_hash: string;
  status: "pending" | "processing" | "ready" | "failed";
  error_message: string;
  chunk_count: number;
  created_at: number;
  updated_at: number;
}

export interface KnowledgeEmbeddingOptions {
  onnx: { id: string; name: string; downloaded: boolean }[];
  remote: {
    provider_id: string;
    provider_name: string;
    models: { id: string; name: string }[];
  }[];
}

export const DEFAULT_KNOWLEDGE_LIMITS: KnowledgeLimits = {
  max_bases_per_owner: 20,
  max_docs_per_kb: 100,
  max_document_bytes: 20 * 1024 * 1024,
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
  getEmbeddingOptions: () =>
    request<KnowledgeEmbeddingOptions>("/knowledge-bases/embedding-options"),

  get: (id: string) => request<KnowledgeBase>(`/knowledge-bases/${id}`),

  create: (body: {
    name: string;
    description?: string;
    default_open?: boolean;
    shared?: boolean;
    icon_name?: string;
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
    },
  ) =>
    request<KnowledgeBase>(`/knowledge-bases/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (id: string) =>
    request<void>(`/knowledge-bases/${id}`, { method: "DELETE" }),

  listDocuments: (id: string) =>
    request<KnowledgeDocument[]>(`/knowledge-bases/${id}/documents`),

  uploadDocument: (id: string, file: File) => {
    const body = new FormData();
    body.append("upload", file);
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
};
