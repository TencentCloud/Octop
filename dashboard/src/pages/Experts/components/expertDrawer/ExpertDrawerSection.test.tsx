import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ExpertDrawerSection from "./ExpertDrawerSection";

describe("ExpertDrawerSection", () => {
  it("renders the section as an anchor target with title and action", () => {
    render(
      <ExpertDrawerSection
        id="ed-section-identity"
        title="Identity"
        action={<button type="button">manage</button>}
      >
        <span>fields</span>
      </ExpertDrawerSection>,
    );

    const section = document.getElementById("ed-section-identity");
    expect(section).not.toBeNull();
    expect(screen.getByText("Identity")).toBeInTheDocument();
    expect(screen.getByText("fields")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "manage" })).toBeInTheDocument();
  });

  it("falls back to a generated id when none is given", () => {
    render(
      <ExpertDrawerSection title="Advanced">
        <span>runtime</span>
      </ExpertDrawerSection>,
    );
    const sections = document.querySelectorAll("section");
    expect(sections).toHaveLength(1);
    expect(sections[0].id).toMatch(/^ed-section-/);
  });
});
