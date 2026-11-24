import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import ExpertDrawerCollapsible from "./ExpertDrawerCollapsible";

describe("ExpertDrawerCollapsible", () => {
  it("keeps children collapsed (but mounted) until opened", () => {
    render(
      <ExpertDrawerCollapsible title="experts.advancedOptions">
        <span>experts.defaultModeLabel</span>
      </ExpertDrawerCollapsible>,
    );

    const toggle = screen.getByRole("button", {
      name: /experts\.advancedOptions/,
    });
    const content = screen.getByText("experts.defaultModeLabel");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // Children stay mounted while hidden so a save without expanding still
    // submits their form values.
    expect(content.parentElement).toHaveStyle({ display: "none" });
    expect(toggle.querySelector("svg")).not.toBeNull();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(content.parentElement).not.toHaveStyle({ display: "none" });
    expect(content).toBeVisible();
  });
});
