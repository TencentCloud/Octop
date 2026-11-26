import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createInstance } from "i18next";
import en from "../../../locales/en.json";
import zh from "../../../locales/zh.json";
import SecretFileCard from "./SecretFileCard";
import type { SecretRequest } from "../../../api/types/hitl";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
  }),
}));

const request: SecretRequest = {
  path: "hr.token",
  prompt: "HR 系统的访问 Token",
  meta: { path: "/home/u/.octop/agents/a1/.octop/auth/hr.token" },
};

function renderCard(overrides?: {
  meta?: SecretRequest["meta"];
  status?: "pending" | "approved" | "rejected";
  onSubmit?: (content: string) => Promise<string | null>;
  onCancel?: () => void;
}) {
  return render(
    <SecretFileCard
      request={{ ...request, meta: overrides?.meta ?? request.meta }}
      status={overrides?.status ?? "pending"}
      onSubmit={overrides?.onSubmit ?? vi.fn().mockResolvedValue(null)}
      onCancel={overrides?.onCancel ?? vi.fn()}
    />,
  );
}

describe("SecretFileCard", () => {
  it.each(["en", "zh"])("interpolates the stored path in %s", async (lng) => {
    const translator = createInstance();
    await translator.init({
      lng,
      interpolation: { escapeValue: false },
      resources: { en: { translation: en }, zh: { translation: zh } },
    });
    expect(
      translator.t("chat.secretCard.filledSummary", {
        path: "auth/demo.token",
      }),
    ).toContain("auth/demo.token");
  });

  it("shows purpose and normalized target path", () => {
    renderCard();
    expect(screen.getByText("HR 系统的访问 Token")).toBeInTheDocument();
    expect(
      screen.getByText("/home/u/.octop/agents/a1/.octop/auth/hr.token"),
    ).toBeInTheDocument();
  });

  it("warns when the file already exists (replace)", () => {
    renderCard({ meta: { path: "hr.token", exists: true } });
    expect(
      screen.getByText("chat.secretCard.replaceWarning"),
    ).toBeInTheDocument();
  });

  it("blocks submission for an invalid path", () => {
    const onSubmit = vi.fn().mockResolvedValue(null);
    renderCard({ meta: { invalid: true }, onSubmit });
    expect(screen.getByText("chat.secretCard.invalidPath")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(/placeholder/),
    ).not.toBeInTheDocument();
  });

  it("blocks submission when the backend cannot store privately", () => {
    const onSubmit = vi.fn().mockResolvedValue(null);
    renderCard({ meta: { invalid: true, unsupported: true }, onSubmit });
    expect(screen.getByText("chat.secretCard.unsupported")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(/placeholder/),
    ).not.toBeInTheDocument();
  });

  it("clears the input after a successful submit", async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);
    renderCard({ onSubmit });
    const input = screen.getByPlaceholderText(/placeholder/);
    fireEvent.change(input, { target: { value: "synthetic-token" } });
    fireEvent.click(screen.getByText("chat.secretCard.submit"));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith("synthetic-token"),
    );
    await waitFor(() =>
      expect(
        (screen.getByPlaceholderText(/placeholder/) as HTMLInputElement).value,
      ).toBe(""),
    );
  });

  it("keeps the draft and shows the error when submit fails (retry allowed)", async () => {
    const onSubmit = vi
      .fn()
      .mockResolvedValueOnce("write failed")
      .mockResolvedValueOnce(null);
    renderCard({ onSubmit });
    const input = screen.getByPlaceholderText(/placeholder/);
    fireEvent.change(input, { target: { value: "synthetic-token" } });
    fireEvent.click(screen.getByText("chat.secretCard.submit"));
    await screen.findByText("write failed");
    // draft kept for retry — the user does not retype
    expect((input as HTMLInputElement).value).toBe("synthetic-token");
    fireEvent.click(screen.getByText("chat.secretCard.submit"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
  });

  it("does not render the typed secret into the DOM", async () => {
    renderCard();
    const input = screen.getByPlaceholderText(/placeholder/);
    fireEvent.change(input, { target: { value: "synthetic-token" } });
    fireEvent.click(screen.getByText("chat.secretCard.submit"));
    await waitFor(() =>
      expect(
        (screen.getByPlaceholderText(/placeholder/) as HTMLInputElement).value,
      ).toBe(""),
    );
    // after clearing, no node text contains the secret
    expect(screen.queryByText(/synthetic-token/)).not.toBeInTheDocument();
  });

  it("renders completed states without the input", () => {
    const { unmount } = renderCard({ status: "approved" });
    expect(screen.getByText(/filledSummary/)).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(/placeholder/),
    ).not.toBeInTheDocument();
    unmount();
    renderCard({ status: "rejected" });
    expect(screen.getByText(/cancelledSummary/)).toBeInTheDocument();
  });
});
