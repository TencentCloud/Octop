import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import NotFoundPage from "./NotFoundPage";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("NotFoundPage", () => {
  it("shows a gentle missing-page message and a path back to chat", () => {
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("common.notFound")).toBeInTheDocument();
    expect(screen.getByText("common.notFoundHint")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "common.backToChat" }),
    ).toBeInTheDocument();
  });
});
