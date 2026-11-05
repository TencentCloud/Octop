/**
 * Vault page test — list/filter/search/create/delete.
 *
 *   - empty list → localized empty state
 *   - items render title, type tag, revealed text value, origin (unverified
 *     label), updated time
 *   - filter tabs show counts and narrow the list by item type
 *   - search filters by title and by revealed text values
 *   - delete goes through Popconfirm and refreshes the list
 *   - creation modal: dropdown picks the type, client validation blocks an
 *     empty submit, a valid submit POSTs and refreshes
 *   - privacy footnote renders under the list
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

vi.mock("../../../api/modules/vault", () => ({
  vaultApi: {
    list: vi.fn(),
    create: vi.fn(),
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
    // Revealable text only — secret values are never returned by the API.
    fields: { text: "alice@example.com" },
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

  it("lists items with type, revealed value, origin, and timestamps", async () => {
    api.list.mockResolvedValue({ items: [item()] });

    render(<VaultPage />);
    await waitFor(() => expect(screen.getByText(/Steam/)).toBeInTheDocument());

    // The type tag renders inside the Steam row (the filter tab shares the
    // item-type label, so scope the assertion to the row).
    const row = screen.getByText(/Steam/).closest("li");
    expect(row).not.toBeNull();
    within(row as HTMLLIElement).getByText("vault.itemType.login");
    within(row as HTMLLIElement).getByText("alice@example.com");
    within(row as HTMLLIElement).getByText("https://steamcommunity.com");
    within(row as HTMLLIElement).getByText("vault.originUnverified");
    within(row as HTMLLIElement).getByText("vault.updatedAt");
  });

  it("renders the privacy footnote under the list", async () => {
    api.list.mockResolvedValue({ items: [item()] });

    render(<VaultPage />);
    await waitFor(() => expect(screen.getByText(/Steam/)).toBeInTheDocument());

    expect(screen.getByText("vault.privacyNote")).toBeInTheDocument();
  });

  it("shows per-type counts on the filter tabs and narrows the list", async () => {
    api.list.mockResolvedValue({
      items: [
        item(),
        item({
          vault_item_id: "vlt2",
          title: "GitLab",
          origin: null,
          fields: {},
        }),
        item({
          vault_item_id: "vlt3",
          item_type: "card",
          title: "Visa",
          fields: {},
        }),
      ],
    });

    render(<VaultPage />);
    await waitFor(() => expect(screen.getByText(/Steam/)).toBeInTheDocument());

    const allTab = screen.getByRole("tab", { name: /vault.filter.all/ });
    expect(allTab).toHaveTextContent("3");
    const cardTab = screen.getByRole("tab", { name: /vault.itemType.card/ });
    expect(cardTab).toHaveTextContent("1");

    fireEvent.click(cardTab);
    expect(screen.getByText(/Visa/)).toBeInTheDocument();
    expect(screen.queryByText(/Steam/)).not.toBeInTheDocument();
    expect(screen.queryByText(/GitLab/)).not.toBeInTheDocument();
  });

  it("searches by title and by revealed text values", async () => {
    api.list.mockResolvedValue({
      items: [
        item(),
        item({ vault_item_id: "vlt2", title: "Mom", fields: {}, origin: null }),
      ],
    });

    render(<VaultPage />);
    await waitFor(() => expect(screen.getByText(/Steam/)).toBeInTheDocument());

    const search = screen.getByPlaceholderText("vault.searchPlaceholder");
    fireEvent.change(search, { target: { value: "mom" } });
    expect(screen.getByText(/Mom/)).toBeInTheDocument();
    expect(screen.queryByText(/Steam/)).not.toBeInTheDocument();

    // Revealed values are searchable too.
    fireEvent.change(search, { target: { value: "alice" } });
    expect(screen.getByText(/Steam/)).toBeInTheDocument();
    expect(screen.queryByText(/Mom/)).not.toBeInTheDocument();

    // No hit → the no-match state, not the empty-vault state.
    fireEvent.change(search, { target: { value: "nomatch" } });
    expect(screen.getByText("vault.noMatch")).toBeInTheDocument();
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

  it("creates an item through the typed modal and refreshes the list", async () => {
    api.list.mockResolvedValueOnce({ items: [] }).mockResolvedValue({
      items: [item({ vault_item_id: "vlt9", origin: null, fields: {} })],
    });
    api.create.mockResolvedValue(item({ vault_item_id: "vlt9" }));

    render(<VaultPage />);
    await waitFor(() => expect(api.list).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole("button", { name: /vault.newItem/ }));
    fireEvent.click(
      await screen.findByRole("menuitem", { name: /vault.itemType.login/ }),
    );

    // Empty submit is blocked client-side with visible validation errors.
    fireEvent.click(
      screen.getByRole("button", { name: "vault.create.submit" }),
    );
    expect(api.create).not.toHaveBeenCalled();
    expect(
      screen.getByText("vault.create.errors.titleRequired"),
    ).toBeInTheDocument();
    // Both typed fields (username + password) show the required error.
    expect(screen.getAllByText("vault.create.errors.required")).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("vault.create.fields.title"), {
      target: { value: "GitHub" },
    });
    fireEvent.change(screen.getByLabelText("vault.create.fields.username"), {
      target: { value: "alice@example.com" },
    });
    fireEvent.change(screen.getByLabelText("vault.create.fields.password"), {
      target: { value: "hunter2" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "vault.create.submit" }),
    );

    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith({
        item_type: "login",
        title: "GitHub",
        origin: undefined,
        fields: [
          { id: "username", type: "text", value: "alice@example.com" },
          { id: "password", type: "password", value: "hunter2" },
        ],
      }),
    );
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(
        screen.queryByText("vault.create.fields.title"),
      ).not.toBeInTheDocument(),
    );
  });

  it("rejects malformed card values inside the creation modal", async () => {
    api.list.mockResolvedValue({ items: [] });

    render(<VaultPage />);
    await waitFor(() => expect(api.list).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole("button", { name: /vault.newItem/ }));
    fireEvent.click(
      await screen.findByRole("menuitem", { name: /vault.itemType.card/ }),
    );

    fireEvent.change(screen.getByLabelText("vault.create.fields.title"), {
      target: { value: "Visa" },
    });
    fireEvent.change(screen.getByLabelText("vault.create.fields.card_number"), {
      target: { value: "4242" },
    });
    fireEvent.change(screen.getByLabelText("vault.create.fields.card_exp"), {
      target: { value: "13/29" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "vault.create.submit" }),
    );

    expect(api.create).not.toHaveBeenCalled();
    expect(
      screen.getByText("vault.create.errors.cardNumber"),
    ).toBeInTheDocument();
    expect(screen.getByText("vault.create.errors.cardExp")).toBeInTheDocument();
  });
});
