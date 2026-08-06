import { request } from "../request";

export interface CustomExpertPreview {
  included_files: string[];
  excluded_sensitive_files: string[];
  ignored_file_count: number;
}

export interface PublishCustomExpertBody {
  template_id: string;
  label_zh: string;
  label_en: string;
  description_zh: string;
  description_en: string;
  icon_name?: string | null;
  color?: string | null;
}

export interface PublishCustomExpertResult {
  template_id: string;
  copied_files: string[];
  excluded_sensitive_files: string[];
}

export const customExpertTemplatesApi = {
  preview: (agentId: string) =>
    request<CustomExpertPreview>(
      `/admin/agents/${agentId}/expert-template/preview`,
    ),

  publish: (agentId: string, body: PublishCustomExpertBody) =>
    request<PublishCustomExpertResult>(
      `/admin/agents/${agentId}/expert-template`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  delete: (templateId: string) =>
    request<void>(`/admin/expert-templates/${templateId}`, {
      method: "DELETE",
    }),
};
