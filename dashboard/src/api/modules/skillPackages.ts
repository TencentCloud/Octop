import { request } from "../request";
import type {
  CreateSkillPackageBody,
  CreateSkillPackageSkillBody,
  SkillPackage,
  SkillPackageDetail,
  SkillPackageSkill,
  SkillPackageSkillDetail,
  UpdateSkillPackageBody,
  UpdateSkillPackageSkillBody,
} from "../types/skillPackage";

export const skillPackagesApi = {
  list: () => request<SkillPackage[]>("/skill-packages"),

  listMounted: (agentId: string) =>
    request<{ package_ids: string[] }>(`/agents/${agentId}/skill-packages`),

  replaceMounted: (agentId: string, packageIds: string[]) =>
    request<{ package_ids: string[] }>(`/agents/${agentId}/skill-packages`, {
      method: "PUT",
      body: JSON.stringify({ package_ids: packageIds }),
    }),

  get: (packageId: string) =>
    request<SkillPackageDetail>(`/skill-packages/${packageId}`),

  create: (body: CreateSkillPackageBody) =>
    request<SkillPackageDetail>("/skill-packages", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  fromSkillHub: (body: {
    slug: string;
    name?: string;
    description?: string;
    icon_name?: string;
    icon_url?: string;
  }) =>
    request<SkillPackageDetail>("/skill-packages/from-skillhub", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  update: (packageId: string, body: UpdateSkillPackageBody) =>
    request<SkillPackageDetail>(`/skill-packages/${packageId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (packageId: string) =>
    request<void>(`/skill-packages/${packageId}`, { method: "DELETE" }),

  getSkill: (packageId: string, slug: string) =>
    request<SkillPackageSkillDetail>(
      `/skill-packages/${packageId}/skills/${encodeURIComponent(slug)}`,
    ),

  createSkill: (packageId: string, body: CreateSkillPackageSkillBody) =>
    request<SkillPackageSkill>(`/skill-packages/${packageId}/skills`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateSkill: (
    packageId: string,
    slug: string,
    body: UpdateSkillPackageSkillBody,
  ) =>
    request<SkillPackageSkill>(
      `/skill-packages/${packageId}/skills/${encodeURIComponent(slug)}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    ),

  deleteSkill: (packageId: string, slug: string) =>
    request<void>(
      `/skill-packages/${packageId}/skills/${encodeURIComponent(slug)}`,
      { method: "DELETE" },
    ),

  importSkill: (
    packageId: string,
    body: { bundle_url: string; version?: string; overwrite?: boolean },
  ) =>
    request<SkillPackageSkill>(
      `/skill-packages/${packageId}/skills/import`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  hubSearch: (q: string, limit = 50) =>
    request<Record<string, unknown>[]>(
      `/skill-packages/hub/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),

  hubRankings: (type = "all") =>
    request<Record<string, unknown>>(
      `/skill-packages/hub/rankings?type=${encodeURIComponent(type)}`,
    ),

  hubInstall: (
    packageId: string,
    body: {
      skill_name: string;
      display_name?: string;
      icon_url?: string;
      overwrite?: boolean;
    },
  ) =>
    request<{ installed: boolean; name: string; transport: string }>(
      `/skill-packages/${packageId}/skills/hub/install`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
};
