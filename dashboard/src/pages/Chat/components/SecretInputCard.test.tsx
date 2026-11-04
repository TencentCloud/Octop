import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SecretInputCard from "./SecretInputCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, string>) =>
      params && "slot" in params ? `${key}:${params.slot}` : key,
  }),
}));

const request = {
  slot: "STEAM_WEB_API_KEY",
  prompt: "Steam Web API key",
  title: "Steam key",
};

describe("SecretInputCard", () => {
  it("disables submit until a value is entered", () => {
    render(
      <SecretInputCard request={request} status="pending" onSubmit={vi.fn()} />,
    );
    const submit = screen.getByRole("button", {
      name: "chat.secretInput.submit",
    });
    expect(submit).toBeDisabled();
  });

  it("shows the masked input with the slot chip and never the value", () => {
    render(
      <SecretInputCard request={request} status="pending" onSubmit={vi.fn()} />,
    );
    // Slot rides a compact mono chip in the header (Grok-style).
    expect(screen.getByText(/STEAM_WEB_API_KEY/)).toBeInTheDocument();
    const box = screen.getByPlaceholderText("chat.secretInput.placeholder");
    fireEvent.change(box, { target: { value: "sk-super-secret" } });
    // antd Input.Password masks by default: type=password.
    expect(box).toHaveAttribute("type", "password");
    expect(screen.queryByText(/sk-super-secret/)).not.toBeInTheDocument();
  });

  it("clears the input after a successful submit", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);
    render(
      <SecretInputCard
        request={request}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    const box = screen.getByPlaceholderText(
      "chat.secretInput.placeholder",
    ) as HTMLInputElement;
    fireEvent.change(box, { target: { value: "sk-super-secret" } });
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secretInput.submit" }),
    );
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith("sk-super-secret"),
    );
    await waitFor(() => expect(box.value).toBe(""));
  });

  it("keeps the draft and shows the error after a failed submit", async () => {
    const onSubmit = vi.fn().mockResolvedValue("store failed");
    render(
      <SecretInputCard
        request={request}
        status="pending"
        onSubmit={onSubmit}
      />,
    );
    const box = screen.getByPlaceholderText(
      "chat.secretInput.placeholder",
    ) as HTMLInputElement;
    fireEvent.change(box, { target: { value: "sk-super-secret" } });
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secretInput.submit" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("store failed"),
    );
    expect(box.value).toBe("sk-super-secret");
  });

  it("cancel dismisses without submitting", () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    render(
      <SecretInputCard
        request={request}
        status="pending"
        onSubmit={onSubmit}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "chat.secretInput.cancel" }),
    );
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("renders a status-only summary once resolved", () => {
    const { rerender } = render(
      <SecretInputCard request={request} status="approved" />,
    );
    expect(
      screen.getByText("chat.secretInput.filledSummary:STEAM_WEB_API_KEY"),
    ).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("chat.secretInput.placeholder"),
    ).not.toBeInTheDocument();

    rerender(<SecretInputCard request={request} status="rejected" />);
    expect(
      screen.getByText("chat.secretInput.dismissedSummary:STEAM_WEB_API_KEY"),
    ).toBeInTheDocument();
  });
});
