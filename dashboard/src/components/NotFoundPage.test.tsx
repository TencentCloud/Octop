import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import NotFoundPage from "./NotFoundPage";
import ForbiddenPage from "./ForbiddenPage";

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

describe.each([
  ["not found", NotFoundPage],
  ["forbidden", ForbiddenPage],
])("%s recovery", (_, ErrorPage) => {
  it.each([
    ["/unknown", "/chat"],
    ["/embed/chat/agent-a/thr_1/extra", "/embed/chat/agent-a"],
  ])("returns from %s without changing surfaces", (pathname, destination) => {
    render(
      <MemoryRouter initialEntries={[pathname]}>
        <Routes>
          <Route path="*" element={<ErrorPage />} />
          <Route path={destination} element={<div>recovered chat</div>} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "common.backToChat" }));
    expect(screen.getByText("recovered chat")).toBeInTheDocument();
  });

  it("has no console exit for an embedded path without an agent", () => {
    render(
      <MemoryRouter initialEntries={["/embed/chat"]}>
        <ErrorPage />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("button", { name: "common.backToChat" }),
    ).toBeNull();
  });
});
