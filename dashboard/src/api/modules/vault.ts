import { request } from "../request";

export type VaultItemType = "login" | "card" | "contact";

/** Field types a manually created item may carry (per item-type pairing). */
export type VaultFieldInputType =
  | "text"
  | "password"
  | "card_number"
  | "card_exp";

export interface VaultItem {
  vault_item_id: string;
  item_type: VaultItemType;
  title: string;
  /** Agent-declared site origin, not verified. */
  origin?: string | null;
  /**
   * Revealable values keyed by field type — plain text only (usernames,
   * contact info); password and card values are never returned.
   */
  fields: Record<string, string>;
  created_at: number;
  /** Changes on rotation, so silent rotation stays visible. */
  updated_at: number;
}

export interface VaultItemsResponse {
  items: VaultItem[];
}

export interface VaultItemFieldInput {
  id: string;
  label?: string;
  type: VaultFieldInputType;
  value: string;
}

export interface VaultItemCreateInput {
  item_type: VaultItemType;
  title: string;
  origin?: string;
  fields: VaultItemFieldInput[];
}

export const vaultApi = {
  list: () => request<VaultItemsResponse>("/vault/items"),
  create: (input: VaultItemCreateInput) =>
    request<VaultItem>("/vault/items", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  remove: (vaultItemId: string) =>
    request<{ deleted: boolean }>(
      `/vault/items/${encodeURIComponent(vaultItemId)}`,
      { method: "DELETE" },
    ),
};
