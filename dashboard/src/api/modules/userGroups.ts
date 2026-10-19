import { request } from "../request";

export interface UserGroup {
  user_group_id: string;
  name: string;
  description: string | null;
  member_count: number;
  created_at: number;
  updated_at: number;
}

export type ResourceVisibilityMode = "all" | "groups" | "owner";

export const userGroupsApi = {
  list: () => request<UserGroup[]>("/user-groups"),

  create: (body: { name: string; description?: string | null }) =>
    request<UserGroup>("/user-groups", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  update: (
    userGroupId: string,
    body: { name?: string; description?: string | null },
  ) =>
    request<UserGroup>(`/user-groups/${encodeURIComponent(userGroupId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  remove: (userGroupId: string) =>
    request<void>(`/user-groups/${encodeURIComponent(userGroupId)}`, {
      method: "DELETE",
    }),

  members: (userGroupId: string) =>
    request<{ user_ids: number[] }>(
      `/user-groups/${encodeURIComponent(userGroupId)}/members`,
    ),

  replaceMembers: (userGroupId: string, userIds: number[]) =>
    request<{ user_ids: number[] }>(
      `/user-groups/${encodeURIComponent(userGroupId)}/members`,
      {
        method: "PUT",
        body: JSON.stringify({ user_ids: userIds }),
      },
    ),
};
