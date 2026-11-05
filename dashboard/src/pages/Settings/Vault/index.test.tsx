/**
 * Vault page test — list/delete with metadata only.
 *
 *   - empty list → localized empty state
 *   - items render title, type tag, origin (unverified label), updated time
 *   - delete goes through Popconfirm and refreshes the list
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../../../api/modules/vault", () => ({
  vaultApi: {
    list: vi.fn(),
    remove: vi.fn(),
  },
}));
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

import { vaultApi, type VaultItem } from "../../../api/modules/vault";
import VaultPage from "./index";

const api = vi.mocked(vaultApi, true);

function item(overrides: Partial<VaultItem> = {}): VaultItem {
  return {
    vault_item_id: "vlt1",
    item_type: "login",
    title: "Steam",
    origin: "https://steamcommunity.com",
    created_at: 1700000000,
    updated_at: 1700000100,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<VaultPage />", () => {
  it("shows the localized empty state when the vault has no items", async () => {
    api.list.mockResolvedValue({ items: [] });

    render(<VaultPage />);
    await waitFor(() => expect(api.list).toHaveBeenCalledOnce());

    expect(screen.getByText("vault.empty")).toBeInTheDocument();
  });

  it("lists items with type, origin, and server-timezone timestamps", async () => {
    api.list.mockResolvedValue({ items: [item()] });

    render(<VaultPage />);
    await waitFor(() => expect(screen.getByText(/Steam/)).toBeInTheDocument());

    expect(screen.getByText("vault.itemType.login")).toBeInTheDocument();
    expect(screen.getByText("https://steamcommunity.com")).toBeInTheDocument();
    expect(screen.getByText("vault.originUnverified")).toBeInTheDocument();
    expect(screen.getByText("vault.updatedAt")).toBeInTheDocument();
  });

  it("deletes an item after confirmation and refreshes the list", async () => {
    api.list.mockResolvedValue({ items: [item()] });
    api.remove.mockResolvedValue({ deleted: true });

    render(<VaultPage />);
    await waitFor(() => expect(screen.getByText(/Steam/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /vault.deleteLabel/ }));
    // Popconfirm requires an explicit confirmation before the delete fires.
    expect(api.remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("vault.deleteConfirmOk"));

    await waitFor(() => expect(api.remove).toHaveBeenCalledWith("vlt1"));
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
  });
});
