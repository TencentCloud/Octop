import { request } from "../request";

export interface OnnxCatalogItem {
  id: string;
  name: string;
  recommended: boolean;
  downloaded: boolean;
  size_gb?: number | null;
  hf_source?: string | null;
}

export interface OnnxModelMeta {
  id: string;
  size_gb?: number | null;
  hf_source?: string | null;
  supported?: boolean;
  downloaded?: boolean;
}

export interface OnnxDownloadState {
  status: "idle" | "downloading" | "loading" | "done" | "failed";
  progress: number;
  error?: string | null;
  model_name: string;
  task_id?: string;
}

export interface OnnxServiceStatus {
  enabled: boolean;
  model: string;
  ready: boolean;
  downloaded: boolean;
  cache_dir: string;
  download: OnnxDownloadState;
  local_models: string[];
  presets: string[];
  download_started?: boolean;
  deps_available?: boolean;
  deps_just_installed?: boolean;
}

export const onnxModelApi = {
  getCatalog: () => request<OnnxCatalogItem[]>("/onnx-models/catalog"),
  getModelMeta: (model: string) =>
    request<OnnxModelMeta>(
      `/onnx-models/models/${encodeURIComponent(model)}/meta`,
    ),
  getStatus: () => request<OnnxServiceStatus>("/onnx-models/status"),
  updateConfig: (body: {
    enabled: boolean;
    model: string;
    download_if_missing?: boolean;
  }) =>
    request<OnnxServiceStatus>("/onnx-models/config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  download: (model: string) =>
    request<OnnxDownloadState>("/onnx-models/download", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  test: (model: string) =>
    request<{
      ok: boolean;
      latency_ms?: number | null;
      error?: string | null;
      dim?: number | null;
    }>("/onnx-models/test", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  getDownloadStatus: () =>
    request<OnnxDownloadState>("/onnx-models/download-status"),
  deleteLocal: (model: string) =>
    request<{ ok: boolean; removed: boolean; status: OnnxServiceStatus }>(
      `/onnx-models/local/${encodeURIComponent(model)}`,
      { method: "DELETE" },
    ),

  /** Toggle local ONNX service without forcing a download. */
  setService: async (enabled: boolean) => {
    const st = await onnxModelApi.getStatus();
    return onnxModelApi.updateConfig({
      enabled,
      model: st.model || st.presets[0] || "BAAI/bge-small-zh-v1.5",
      download_if_missing: false,
    });
  },
};
