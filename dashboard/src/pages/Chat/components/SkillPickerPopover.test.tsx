import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { SkillSpec } from "../../Agent/Skills/useSkills";
import SkillPickerPopover from "./SkillPickerPopover";

function skill(
  name: string,
  kind: SkillSpec["kind"],
  enabled = true,
): SkillSpec {
  return {
    slug: name.toLowerCase().replace(/\s+/g, "-"),
    name,
    description: "",
    enabled,
    kind,
  };
}

describe("SkillPickerPopover order", () => {
  it("lists user-installed skills before built-in skills", () => {
    render(
      <MemoryRouter>
        <SkillPickerPopover
          skills={[
            skill("Builtin A", "builtin"),
            skill("My Skill", "workspace"),
            skill("Pack Skill", "package"),
            skill("Builtin B", "builtin"),
            skill("Disabled Mine", "workspace", false),
          ]}
          onSelectSkill={vi.fn()}
        />
      </MemoryRouter>,
    );

    const list = document.querySelector("[data-picker-list]");
    expect(list?.textContent).toMatch(
      /My Skill[\s\S]*Pack Skill[\s\S]*Builtin A[\s\S]*Builtin B/,
    );
    expect(screen.queryByText("Disabled Mine")).not.toBeInTheDocument();
  });
});
