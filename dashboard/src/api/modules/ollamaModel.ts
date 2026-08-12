import { request } from "../request";
import type {
  OllamaModelResponse,
  OllamaDownloadRequest,
  OllamaDownloadTaskResponse,
} from "../types";

export const ollamaModelApi = {
  listOllamaModels: () => request<OllamaModelResponse[]>("/ollama-models"),

  downloadOllamaModel: (body: OllamaDownloadRequest) =>
    request<OllamaDownloadTaskResponse>("/ollama-models/download", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getOllamaDownloadStatus: () =>
    request<OllamaDownloadTaskResponse[]>("/ollama-models/download-status"),

  cancelOllamaDownload: (taskId: string) =>
    request<{ status: string; task_id: string }>(
      `/ollama-models/download/${encodeURIComponent(taskId)}`,
      { method: "DELETE" },
    ),

  deleteOllamaModel: (name: string) =>
    request<{ status: string; name: string }>(
      `/ollama-models/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),

  getService: () =>
    request<{ enabled: boolean; running: boolean }>("/ollama-models/service"),

  setService: (enabled: boolean) =>
    request<{ enabled: boolean; running: boolean }>("/ollama-models/service", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
};
