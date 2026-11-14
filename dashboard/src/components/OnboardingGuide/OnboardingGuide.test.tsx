import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { patchMock, userRef } = vi.hoisted(() => ({
  patchMock: vi.fn(),
  userRef: {
    current: { role: "user", permissions: ["knowledge_bases"] } as {
      role: string;
      permissions: string[];
    },
  },
}));

vi.mock("../../api/modules/preferences", () => ({
  preferencesApi: { patch: patchMock },
}));
vi.mock("../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => userRef.current,
}));
vi.mock("../../hooks/useIsMobile", () => ({
  useIsMobile: () => false,
}));

import OnboardingGuide from "./OnboardingGuide";

function Location() {
  return <div data-testid="location">{useLocation().pathname}</div>;
}

function renderGuide(onClose = vi.fn()) {
  render(
    <MemoryRouter initialEntries={["/token-usage"]}>
      <div data-nav-key="knowledge-bases">nav</div>
      <OnboardingGuide open onClose={onClose} />
      <Routes>
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  );
  return onClose;
}

const button = (name: string) => screen.getByRole("button", { name });
const location = () => screen.getByTestId("location").textContent;

describe("OnboardingGuide", () => {
  beforeEach(() => {
    patchMock.mockReset();
    patchMock.mockResolvedValue({});
    userRef.current = { role: "user", permissions: ["knowledge_bases"] };
  });

  it("introduces only the pages the user can open", () => {
    renderGuide();
    expect(screen.getByText("onboarding.intro.title")).toBeInTheDocument();
    const concepts = screen
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(concepts).toEqual([
      "onboarding.steps.chat.title",
      "onboarding.steps.models.title",
      "onboarding.steps.knowledgeBases.title",
    ]);
  });

  it("opens each step's page and spotlights its sidebar entry", async () => {
    const user = userEvent.setup();
    renderGuide();
    const kbNav = screen.getByText("nav");

    await user.click(button("onboarding.start"));
    expect(location()).toBe("/chat");
    expect(screen.getByText("onboarding.steps.chat.body")).toBeInTheDocument();

    await user.click(button("onboarding.next"));
    expect(location()).toBe("/chat");
    expect(
      screen.getByText("onboarding.steps.models.bodyMember"),
    ).toBeInTheDocument();
    expect(kbNav).not.toHaveAttribute("data-onboarding-active");

    await user.click(button("onboarding.next"));
    expect(location()).toBe("/knowledge-bases");
    expect(kbNav).toHaveAttribute("data-onboarding-active");
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "3",
    );

    await user.click(button("onboarding.back"));
    expect(kbNav).not.toHaveAttribute("data-onboarding-active");
    expect(patchMock).not.toHaveBeenCalled();
  });

  it("ends on a wrap-up card and records completion", async () => {
    const user = userEvent.setup();
    const onClose = renderGuide();

    await user.click(button("onboarding.start"));
    await user.click(button("onboarding.next"));
    await user.click(button("onboarding.next"));
    await user.click(button("onboarding.finish"));

    expect(screen.getByText("onboarding.done.title")).toBeInTheDocument();
    expect(patchMock).not.toHaveBeenCalled();

    await user.click(button("onboarding.done.chat"));
    expect(location()).toBe("/chat");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(patchMock).toHaveBeenCalledWith({ onboarding_completed: true });
  });

  it("supports arrow keys and Esc during the tour", async () => {
    const user = userEvent.setup();
    const onClose = renderGuide();

    await user.click(button("onboarding.start"));
    act(() => {
      fireEvent.keyDown(window, { key: "ArrowRight" });
    });
    act(() => {
      fireEvent.keyDown(window, { key: "ArrowRight" });
    });
    expect(location()).toBe("/knowledge-bases");
    act(() => {
      fireEvent.keyDown(window, { key: "ArrowLeft" });
    });
    expect(
      screen.getByText("onboarding.steps.models.bodyMember"),
    ).toBeInTheDocument();

    act(() => {
      fireEvent.keyDown(window, { key: "Escape" });
    });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(patchMock).toHaveBeenCalledWith({ onboarding_completed: true });
  });

  it("records completion when postponed from the intro", async () => {
    const user = userEvent.setup();
    const onClose = renderGuide();

    await user.click(button("onboarding.later"));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(patchMock).toHaveBeenCalledWith({ onboarding_completed: true });
    expect(location()).toBe("/token-usage");
  });

  it("offers the experts page at the end when the user can open it", async () => {
    userRef.current = { role: "admin", permissions: [] };
    const user = userEvent.setup();
    renderGuide();

    await user.click(button("onboarding.start"));
    for (let i = 0; i < 5; i += 1) {
      await user.click(button("onboarding.next"));
    }
    expect(location()).toBe("/skill-packages");
    await user.click(button("onboarding.finish"));
    await user.click(button("onboarding.done.experts"));

    expect(location()).toBe("/experts");
    expect(patchMock).toHaveBeenCalledWith({ onboarding_completed: true });
  });
});
