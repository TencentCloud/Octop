import { request, requestUpload } from "../request";

export interface UploadResponse {
  path: string;
  workspace_path: string;
  filename: string;
  media_type: string;
  url: string;
  access_url: string;
  preview_url?: string;
}

/**
 * Upload a chat attachment into the agent workspace ``inbound/`` directory.
 */
export async function uploadFile(
  agentId: string,
  file: File,
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return requestUpload<UploadResponse>(`/agents/${agentId}/upload`, formData);
}

export const uploadImage = uploadFile;

export type NativeCaptureMode = "scan" | "photo" | "album";

export function nativeCaptureAvailability(agentId: string) {
  return request<{ available: boolean }>(`/agents/${agentId}/native-capture`);
}

export function captureNativeAttachment(
  agentId: string,
  mode: NativeCaptureMode = "scan",
) {
  return request<{
    status: "ok" | "cancelled" | "timeout" | "unavailable" | "error" | "busy";
    attachments: UploadResponse[];
  }>(`/agents/${agentId}/native-capture`, {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
}

export const uploadApi = { uploadFile, uploadImage };
