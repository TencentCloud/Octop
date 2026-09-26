import type { TFunction } from "i18next";
import { request, requestUpload } from "../request";

export interface RolePolicy {
  name: string;
  value: string;
}

export interface UserRole {
  user_role_id: string;
  user_role_name: string;
  description: string | null;
  system_role: "admin" | "user";
  permissions: string[];
  policies: RolePolicy[];
  deletable: boolean;
  immutable: boolean;
  workspace_root_dir: string | null;
  token_quota: number | null;
  max_agents: number | null;
  created_at: number;
  updated_at: number;
  avatar_url?: string | null;
  avatar_icon?: string | null;
}

export interface UserRoleWriteBody {
  user_role_name: string;
  description?: string | null;
  permissions?: string[];
  policies?: RolePolicy[];
  avatar_icon?: string | null;
}

export const SEEDED_ADMIN_ROLE_ID = "admin";
export const SEEDED_USER_ROLE_ID = "user";
const SEEDED_ADMIN_ROLE_NAME = "管理员";
const SEEDED_USER_ROLE_NAME = "用户";

export const userRolesApi = {
  list: () => request<UserRole[]>("/users/roles"),

  create: (body: UserRoleWriteBody) =>
    request<UserRole>("/users/roles", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  update: (userRoleId: string, body: Partial<UserRoleWriteBody>) =>
    request<UserRole>(`/users/roles/${encodeURIComponent(userRoleId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  remove: (userRoleId: string) =>
    request<void>(`/users/roles/${encodeURIComponent(userRoleId)}`, {
      method: "DELETE",
    }),

  uploadAvatar: (userRoleId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return requestUpload<{ avatar_url: string | null }>(
      `/users/roles/${encodeURIComponent(userRoleId)}/avatar`,
      body,
    );
  },

  deleteAvatar: (userRoleId: string) =>
    request<void>(`/users/roles/${encodeURIComponent(userRoleId)}/avatar`, {
      method: "DELETE",
    }),
};

/** Seeded admin/user names stay translatable until an admin renames them. */
export function userRoleLabel(
  role: Pick<UserRole, "user_role_id" | "user_role_name">,
  t: TFunction,
): string {
  if (
    role.user_role_id === SEEDED_ADMIN_ROLE_ID &&
    role.user_role_name === SEEDED_ADMIN_ROLE_NAME
  ) {
    return t("adminUsers.seedRoleAdmin");
  }
  if (
    role.user_role_id === SEEDED_USER_ROLE_ID &&
    role.user_role_name === SEEDED_USER_ROLE_NAME
  ) {
    return t("adminUsers.seedRoleUser");
  }
  return role.user_role_name;
}

export function userRoleDescription(role: UserRole, t: TFunction): string {
  if (role.description) return role.description;
  if (role.user_role_id === SEEDED_ADMIN_ROLE_ID) {
    return t("adminUsers.seedRoleAdminDescription");
  }
  if (role.user_role_id === SEEDED_USER_ROLE_ID) {
    return t("adminUsers.seedRoleUserDescription");
  }
  return t("adminUsers.roleDescriptionEmpty");
}

export function snapshotRoleLabel(
  name: string | null | undefined,
  roles: UserRole[],
  t: TFunction,
  userRoleId?: string | null,
): string {
  const trimmed = name?.trim();
  if (!trimmed) return "";
  const match = userRoleId
    ? roles.find((role) => role.user_role_id === userRoleId)
    : roles.find((role) => role.user_role_name === trimmed);
  return match ? userRoleLabel(match, t) : trimmed;
}

export type UserRoleDrift = "missing" | "changed";

export function userRoleDrift(
  row: {
    role_name?: string | null;
    user_role_id?: string | null;
    permissions?: string[];
    workspace_root_dir?: string | null;
    token_quota?: number | null;
    max_agents?: number | null;
  },
  roles: UserRole[],
): UserRoleDrift | null {
  const name = row.role_name?.trim();
  if (!name) return null;
  const role = row.user_role_id
    ? roles.find((item) => item.user_role_id === row.user_role_id)
    : roles.find((item) => item.user_role_name === name);
  if (!role) return "missing";
  if (role.system_role === "admin") return null;
  const left = [...(row.permissions ?? [])].sort().join("\0");
  const right = [...role.permissions].sort().join("\0");
  if (left !== right) return "changed";
  const root = row.workspace_root_dir?.trim() || null;
  const roleRoot = role.workspace_root_dir?.trim() || null;
  if (root !== roleRoot) return "changed";
  if ((row.token_quota ?? null) !== (role.token_quota ?? null)) return "changed";
  if ((row.max_agents ?? null) !== (role.max_agents ?? null)) return "changed";
  return null;
}
