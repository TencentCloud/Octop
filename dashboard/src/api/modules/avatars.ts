import { request, requestUpload } from "../request";

export interface AvatarUploadResult {
  avatar_url: string;
  kind: "users" | "agents";
  key: string;
}

function formDataWithFile(file: File): FormData {
  const form = new FormData();
  form.append("file", file);
  return form;
}

/** Upload (or replace) the current user's avatar. */
export function uploadUserAvatar(file: File): Promise<AvatarUploadResult> {
  return requestUpload<AvatarUploadResult>(
    "/avatars/users/me",
    formDataWithFile(file),
  );
}

/** Upload (or replace) an agent/expert avatar. */
export function uploadAgentAvatar(
  agentId: string,
  file: File,
): Promise<AvatarUploadResult> {
  return requestUpload<AvatarUploadResult>(
    `/avatars/agents/${encodeURIComponent(agentId)}`,
    formDataWithFile(file),
  );
}

/** Delete the current user's avatar (falls back to initials). */
export function deleteUserAvatar(): Promise<void> {
  return request("/avatars/users/me", { method: "DELETE" });
}

/** Delete an agent/expert avatar (falls back to icon + color). */
export function deleteAgentAvatar(agentId: string): Promise<void> {
  return request(`/avatars/agents/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
  });
}
