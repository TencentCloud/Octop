import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import MoreConfigCollapse from "./MoreConfigCollapse";

describe("MoreConfigCollapse", () => {
  it("keeps extra settings collapsed until opened", () => {
    render(
      <MoreConfigCollapse>
        <span>experts.defaultModeLabel</span>
      </MoreConfigCollapse>,
    );

    const toggle = screen.getByRole("button", { name: "experts.moreConfig" });
    const content = screen.getByText("experts.defaultModeLabel");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(content.parentElement).toHaveStyle({ display: "none" });
    expect(toggle.querySelector("svg")).not.toBeNull();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(content.parentElement).not.toHaveStyle({ display: "none" });
    expect(content).toBeVisible();
  });
});
