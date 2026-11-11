import { render, screen } from "@testing-library/react";
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
    <MemoryRouter initialEntries={["/chat"]}>
      <OnboardingGuide open onClose={onClose} />
      <Routes>
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  );
  return onClose;
}

const button = (name: string) => screen.getByRole("button", { name });

describe("OnboardingGuide", () => {
  beforeEach(() => {
    patchMock.mockReset();
    patchMock.mockResolvedValue({});
    userRef.current = { role: "user", permissions: ["knowledge_bases"] };
  });

  it("walks through the steps the user can open", async () => {
    const user = userEvent.setup();
    renderGuide();

    expect(
      screen.getByText("onboarding.steps.welcome.title"),
    ).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuemax",
      "4",
    );

    await user.click(button("onboarding.start"));
    expect(screen.getByText("onboarding.steps.chat.title")).toBeInTheDocument();

    await user.click(button("onboarding.next"));
    expect(
      screen.getByText("onboarding.steps.models.bodyMember"),
    ).toBeInTheDocument();

    await user.click(button("onboarding.back"));
    expect(screen.getByText("onboarding.steps.chat.title")).toBeInTheDocument();

    await user.click(button("onboarding.next"));
    await user.click(button("onboarding.next"));
    expect(
      screen.getByText("onboarding.steps.knowledgeBases.title"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "onboarding.skip" }),
    ).toBeNull();
    expect(patchMock).not.toHaveBeenCalled();
  });

  it("marks the guide done on the server when skipped", async () => {
    const user = userEvent.setup();
    const onClose = renderGuide();

    await user.click(button("onboarding.skip"));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(patchMock).toHaveBeenCalledWith({ onboarding_completed: true });
  });

  it("marks the guide done when finished", async () => {
    const user = userEvent.setup();
    const onClose = renderGuide();

    for (const name of [
      "onboarding.start",
      "onboarding.next",
      "onboarding.next",
    ]) {
      await user.click(button(name));
    }
    await user.click(button("onboarding.finish"));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(patchMock).toHaveBeenCalledWith({ onboarding_completed: true });
  });

  it("opens the step's page and marks the guide done", async () => {
    userRef.current = { role: "admin", permissions: [] };
    const user = userEvent.setup();
    const onClose = renderGuide();

    await user.click(button("onboarding.start"));
    await user.click(button("onboarding.next"));
    await user.click(button("onboarding.next"));
    await user.click(button("onboarding.steps.models.go"));

    expect(screen.getByTestId("location")).toHaveTextContent("/admin/models");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(patchMock).toHaveBeenCalledWith({ onboarding_completed: true });
  });
});
