import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SecureFormCard from "./SecureFormCard";
import { agentChatApi } from "../../../api/modules/agentChat";
import type { SecureFormPendingRecord } from "../../../api/types/hitl";
import type { SecureFormSubmitOutcome } from "../hooks/chatStore";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string | number>) =>
      params && Object.keys(params).length > 0
        ? `${key}:${Object.values(params).join(",")}`
        : key,
  }),
}));

vi.mock("../../../api/modules/agentChat", () => ({
  agentChatApi: { secureForm: vi.fn() },
}));

const fetchRecord = vi.mocked(agentChatApi.secureForm);

const launcher = {
  title: "Steam login",
  prompt: "Model prompt text",
  fieldCount: 3,
};

function envRecord(
  overrides: Partial<SecureFormPendingRecord> = {},
): SecureFormPendingRecord {
  return {
    pending_id: "sf1",
    thread_id: "thread-1",
    agent_id: "agent-1",
    title: "Model title",
    prompt: "Model prompt text",
    status: "pending",
    fields: [
      {
        id: "username",
        label: "Username",
        type: "text",
        required: true,
        max_length: 64,
      },
      {
        id: "password",
        label: "Password",
        type: "password",
        required: true,
        max_length: 128,
      },
      {
        id: "otp",
        label: "Login code",
        type: "otp",
        required: false,
        max_length: 8,
      },
    ],
    routing: {
      kind: "env",
      slots: { username: "SVC_USER", password: "SVC_PASS", otp: "SVC_OTP" },
      vault_meta: null,
    },
    existing_vault_item_id: null,
    existing_slot_names: ["SVC_PASS"],
    vault_storable_field_ids: [],
    ...overrides,
  };
}

function vaultRecord(
  overrides: Partial<SecureFormPendingRecord> = {},
): SecureFormPendingRecord {
  return envRecord({
    fields: [
      {
        id: "username",
        label: "Username",
        type: "text",
        required: true,
        max_length: 64,
      },
      {
        id: "password",
        label: "Password",
        type: "password",
        required: true,
        max_length: 128,
      },
    ],
    routing: {
      kind: "vault",
      slots: null,
      vault_meta: {
        item_type: "login",
        title: "Steam",
        origin: "https://steamcommunity.com",
      },
    },
    existing_slot_names: [],
    vault_storable_field_ids: ["username", "password"],
    ...overrides,
  });
}

/** Resolve a field input whether it is plain-labelled or masked (aria-label). */
function fieldInput(label: string): HTMLElement {
  return (
    screen.queryByLabelText(label) ??
    screen.getByLabelText(`chat.secureForm.maskedFieldAria:${label}`)
  );
}

async function openModal(record: SecureFormPendingRecord) {
  fetchRecord.mockResolvedValueOnce(record);
  render(
    <SecureFormCard
      agentId="agent-1"
      pendingId="sf1"
      request={launcher}
      status="pending"
      onSubmit={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "chat.secureForm.open" }));
  await waitFor(() =>
    expect(fieldInput(record.fields[0].label)).toBeInTheDocument(),
  );
  expect(fetchRecord).toHaveBeenCalledWith("agent-1", "sf1");
}

function fill(label: string, value: string) {
  fireEvent.change(fieldInput(label), {
    target: { value },
  });
}

beforeEach(() => {
  fetchRecord.mockReset();
});

describe("SecureFormCard", () => {
  it("renders the launcher and fetches the server record on open", async () => {
    await openModal(envRecord());
    // Fields come from the GET record, never from tool_start args.
    expect(fieldInput("Username")).toBeInTheDocument();
    expect(fieldInput("Password")).toBeInTheDocument();
  });

  it("masks secret inputs with reveal, new-password autocomplete, and aria labels", async () => {
    await openModal(envRecord());
    const password = screen.getByLabelText(
      "chat.secureForm.maskedFieldAria:Password",
    ) as HTMLInputElement;
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "new-password");
    fireEvent.change(password, { target: { value: "hunter2-secret" } });
    expect(screen.queryByText(/hunter2-secret/)).not.toBeInTheDocument();
    // Plain text fields stay unmasked.
    expect(screen.getByLabelText("Username")).toHaveAttribute("type", "text");
  });

  it("gates submit on per-type validation", async () => {
    await openModal(envRecord());
    const submit = screen.getByRole("button", {
      name: "chat.secureForm.submit",
    });
    // Required fields empty.
    expect(submit).toBeDisabled();
    fill("Username", "alice");
    fill("Password", "hunter2");
    // Optional OTP filled with a bad shape.
    fill("Login code", "12");
    expect(submit).toBeDisabled();
    expect(screen.getByText("chat.secureForm.errors.otp")).toBeInTheDocument();
    fill("Login code", "123456");
    expect(submit).toBeEnabled();
  });

  it("validates card shapes client-side", async () => {
    await openModal(
      envRecord({
        fields: [
          {
            id: "card",
            label: "Card number",
            type: "card_number",
            required: true,
            max_length: 23,
          },
          {
            id: "exp",
            label: "Expiry",
            type: "card_exp",
            required: true,
            max_length: 5,
          },
          {
            id: "cvv",
            label: "CVV",
            type: "card_cvv",
            required: true,
            max_length: 4,
          },
        ],
        routing: {
          kind: "env",
          slots: { card: "SVC_CARD", exp: "SVC_EXP", cvv: "SVC_CVV" },
          vault_meta: null,
        },
      }),
    );
    const submit = screen.getByRole("button", {
      name: "chat.secureForm.submit",
    });
    expect(submit).toBeDisabled();
    fill("Card number", "4111");
    expect(
      screen.getByText("chat.secureForm.errors.cardNumber"),
    ).toBeInTheDocument();
    fill("Card number", "4111 1111 1111 1111");
    expect(submit).toBeDisabled();
    fill("Expiry", "13/26");
    expect(
      screen.getByText("chat.secureForm.errors.cardExp"),
    ).toBeInTheDocument();
    fill("Expiry", "12/26");
    expect(submit).toBeDisabled();
    fill("CVV", "12");
    expect(
      screen.getByText("chat.secureForm.errors.cardCvv"),
    ).toBeInTheDocument();
    fill("CVV", "123");
    expect(submit).toBeEnabled();
  });

  it("renders the trust banner from server facts, not model copy", async () => {
    await openModal(envRecord());
    const banner = screen.getByTestId("secure-form-banner");
    // Slot names are server facts rendered through i18next.
    expect(within(banner).getByText("SVC_USER")).toBeInTheDocument();
    expect(within(banner).getByText("SVC_PASS")).toBeInTheDocument();
    expect(
      within(banner).getByText("chat.secureForm.banner.replacesSlot"),
    ).toBeInTheDocument();
    expect(
      within(banner).getByText("chat.secureForm.banner.envPersist"),
    ).toBeInTheDocument();
    // Model-authored copy renders below the banner, never inside it.
    expect(
      within(banner).queryByText("Model prompt text"),
    ).not.toBeInTheDocument();
    // The prompt shows twice — launcher card and the modal's subordinate copy.
    expect(screen.getAllByText("Model prompt text").length).toBe(2);
    expect(screen.getByText("Model title")).toBeInTheDocument();
  });

  it("labels vault origins as agent-declared and not verified", async () => {
    await openModal(vaultRecord());
    const banner = screen.getByTestId("secure-form-banner");
    expect(
      within(banner).getByText("https://steamcommunity.com"),
    ).toBeInTheDocument();
    expect(
      within(banner).getByText("chat.secureForm.banner.originUnverified"),
    ).toBeInTheDocument();
    expect(
      within(banner).getByText(
        "chat.secureForm.banner.vaultItem:chat.secureForm.itemType.login",
      ),
    ).toBeInTheDocument();
    // Vault routing has no env-persist line.
    expect(
      within(banner).queryByText("chat.secureForm.banner.envPersist"),
    ).not.toBeInTheDocument();
  });

  it("clears values and closes the modal on success", async () => {
    const onSubmit = vi
      .fn()
      .mockResolvedValue({ kind: "success" } as SecureFormSubmitOutcome);
    fetchRecord.mockResolvedValueOnce(envRecord());
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    fill("Username", "alice");
    fill("Password", "hunter2");
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    );
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.action).toBe("submit");
    expect(payload.values).toEqual({ username: "alice", password: "hunter2" });
    // Drafts are dropped: the masked inputs unmount with the modal.
    await waitFor(() =>
      expect(screen.queryByLabelText("Username")).not.toBeInTheDocument(),
    );
  });

  it("keeps drafts and shows a banner on write failure", async () => {
    const onSubmit = vi.fn().mockResolvedValue({
      kind: "error",
      code: "SECURE_FORM_WRITE_FAILED",
      message: "storage failed",
    } as SecureFormSubmitOutcome);
    fetchRecord.mockResolvedValueOnce(envRecord());
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    fill("Username", "alice");
    fill("Password", "hunter2");
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("storage failed"),
    );
    expect((screen.getByLabelText("Username") as HTMLInputElement).value).toBe(
      "alice",
    );
    expect(fetchRecord).toHaveBeenCalledTimes(1);
  });

  it("maps pre-claim field errors onto the field", async () => {
    const onSubmit = vi.fn().mockResolvedValue({
      kind: "error",
      code: "SECURE_FORM_FIELD_INVALID",
      message: "field 'password' is required",
      details: { field: "password" },
    } as SecureFormSubmitOutcome);
    fetchRecord.mockResolvedValueOnce(envRecord());
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    fill("Username", "alice");
    fill("Password", "hunter2");
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    );
    await waitFor(() =>
      expect(
        screen
          .getAllByRole("alert")
          .some(
            (node) =>
              node.textContent?.includes("field 'password' is required"),
          ),
      ).toBe(true),
    );
  });

  it("re-fetches facts and requires replace confirmation after VAULT_REPLACE_REQUIRED", async () => {
    const onSubmit = vi.fn();
    fetchRecord
      .mockResolvedValueOnce(vaultRecord({ existing_vault_item_id: null }))
      .mockResolvedValueOnce(vaultRecord({ existing_vault_item_id: "vlt1" }));
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    fill("Username", "alice");
    fill("Password", "hunter2");
    expect(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    ).toBeEnabled();

    // First submit hits an unconfirmed overwrite that appeared post-registration.
    onSubmit.mockResolvedValueOnce({
      kind: "error",
      code: "VAULT_REPLACE_REQUIRED",
      message: "a login item titled 'Steam' already exists",
    } as SecureFormSubmitOutcome);
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    );
    await waitFor(() => expect(fetchRecord).toHaveBeenCalledTimes(2));
    // The refreshed record now carries existing_vault_item_id.
    await waitFor(() =>
      expect(
        screen.getByText("chat.secureForm.replaceConfirm"),
      ).toBeInTheDocument(),
    );
    // Drafts survived the refusal.
    expect((screen.getByLabelText("Username") as HTMLInputElement).value).toBe(
      "alice",
    );
    // Submit stays disabled until the user explicitly confirms the replace.
    expect(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByText("chat.secureForm.replaceConfirm"));
    const submit = screen.getByRole("button", {
      name: "chat.secureForm.submit",
    });
    await waitFor(() => expect(submit).toBeEnabled());

    onSubmit.mockResolvedValueOnce({
      kind: "success",
    } as SecureFormSubmitOutcome);
    fireEvent.click(submit);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    expect(onSubmit.mock.calls[1][0].replaceConfirmed).toBe(true);
    expect(onSubmit.mock.calls[1][0].values).toEqual({
      username: "alice",
      password: "hunter2",
    });
  });

  it("renders a terminal expired state with no retry", async () => {
    const onSubmit = vi.fn().mockResolvedValue({
      kind: "error",
      code: "SECURE_FORM_PENDING_EXPIRED",
      message: "expired",
    } as SecureFormSubmitOutcome);
    fetchRecord.mockResolvedValueOnce(envRecord());
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    fill("Username", "alice");
    fill("Password", "hunter2");
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    );
    await waitFor(() =>
      expect(
        screen.getByText("chat.secureForm.expiredSummary"),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: "chat.secureForm.open" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
  });

  it("renders terminal handled on 409 replay", async () => {
    const onSubmit = vi.fn().mockResolvedValue({
      kind: "error",
      code: "SECURE_FORM_ALREADY_HANDLED",
      message: "already handled",
    } as SecureFormSubmitOutcome);
    fetchRecord.mockResolvedValueOnce(envRecord());
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    fill("Username", "alice");
    fill("Password", "hunter2");
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.submit" }),
    );
    await waitFor(() =>
      expect(
        screen.getByText("chat.secureForm.handledSummary"),
      ).toBeInTheDocument(),
    );
  });

  it("cancel submits a cancel action without values", async () => {
    const onSubmit = vi
      .fn()
      .mockResolvedValue({ kind: "success" } as SecureFormSubmitOutcome);
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.cancel" }),
    );
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit.mock.calls[0][0]).toEqual({ action: "cancel" });
  });

  it("offers save-to-vault only when the record registered vault metadata on env routing", async () => {
    const withVaultMeta = envRecord({
      vault_storable_field_ids: ["username", "password"],
      routing: {
        kind: "env",
        slots: { username: "SVC_USER", password: "SVC_PASS", otp: "SVC_OTP" },
        vault_meta: { item_type: "login", title: "Steam" },
      },
    });
    fetchRecord.mockResolvedValueOnce(withVaultMeta);
    const first = render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={vi.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    expect(screen.getByText("chat.secureForm.saveToVault")).toBeInTheDocument();
    const banner = screen.getByTestId("secure-form-banner");
    expect(
      within(banner).getByText(
        "chat.secureForm.banner.saveScope:chat.secureForm.fieldType.text, chat.secureForm.fieldType.password",
      ),
    ).toBeInTheDocument();
    first.unmount();

    // No vault_meta registered → no checkbox.
    fetchRecord.mockResolvedValueOnce(envRecord());
    render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="pending"
        onSubmit={vi.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secureForm.open" }),
    );
    await waitFor(() => expect(fetchRecord).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByLabelText("Username")).toBeInTheDocument(),
    );
    expect(
      screen.queryByText("chat.secureForm.saveToVault"),
    ).not.toBeInTheDocument();
  });

  it("renders a status-only summary once resolved", () => {
    const { rerender } = render(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="approved"
      />,
    );
    expect(
      screen.getByText("chat.secureForm.filledSummary:3"),
    ).toBeInTheDocument();
    rerender(
      <SecureFormCard
        agentId="agent-1"
        pendingId="sf1"
        request={launcher}
        status="rejected"
      />,
    );
    expect(
      screen.getByText("chat.secureForm.dismissedSummary:3"),
    ).toBeInTheDocument();
  });
});
