import { request } from "../request";

export type VaultItemType = "login" | "card" | "contact";

export interface VaultItem {
  vault_item_id: string;
  item_type: VaultItemType;
  title: string;
  /** Agent-declared site origin, not verified. */
  origin?: string | null;
  created_at: number;
  /** Changes on rotation, so silent rotation stays visible. */
  updated_at: number;
}

export interface VaultItemsResponse {
  items: VaultItem[];
}

export const vaultApi = {
  /** Metadata only — ciphertext and values are never returned. */
  list: () => request<VaultItemsResponse>("/vault/items"),
  remove: (vaultItemId: string) =>
    request<{ deleted: boolean }>(
      `/vault/items/${encodeURIComponent(vaultItemId)}`,
      { method: "DELETE" },
    ),
};
