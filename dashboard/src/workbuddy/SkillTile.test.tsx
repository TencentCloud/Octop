import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SkillCard } from "../pages/Agent/Skills/components/SkillCard";
import { PackageSkillCard } from "../pages/SkillPackages/PackageSkillCard";

vi.mock("./variant", () => ({ WORKBUDDY_UI: true }));
const skill = {
  slug: "meeting-notes",
  name: "Meeting notes",
  description: "Notes",
  enabled: true,
  kind: "workspace" as const,
};
const defaults = {
  isHover: false,
  onMouseEnter: vi.fn(),
  onMouseLeave: vi.fn(),
};
describe("WorkBuddy skill bindings", () => {
  it("disallows deletion while enabled and forwards a toggle without opening detail", async () => {
    const onClick = vi.fn(),
      onToggleEnabled = vi.fn(),
      onDelete = vi.fn();
    render(
      <SkillCard
        {...defaults}
        skill={skill}
        onClick={onClick}
        onToggleEnabled={onToggleEnabled}
        onDelete={onDelete}
      />,
    );
    expect(
      screen.getByRole("button", { name: "common.delete" }),
    ).toBeDisabled();
    await userEvent.click(screen.getByRole("switch"));
    expect(onToggleEnabled).toHaveBeenCalledOnce();
    expect(onClick).not.toHaveBeenCalled();
    expect(onDelete).not.toHaveBeenCalled();
  });
  it("keeps detail usable without a mount toggle and permits deletion only when disabled", async () => {
    const onClick = vi.fn(),
      onDelete = vi.fn();
    render(
      <SkillCard
        {...defaults}
        skill={{ ...skill, enabled: false }}
        onClick={onClick}
        onToggleEnabled={vi.fn()}
        onDelete={onDelete}
        showEnableToggle={false}
      />,
    );
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "common.delete" }),
    );
    expect(onDelete).toHaveBeenCalledOnce();
    expect(onClick).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: skill.name }));
    expect(onClick).toHaveBeenCalledOnce();
  });
  it("hides package deletion for a reader", () => {
    render(
      <PackageSkillCard
        skill={{
          slug: "notes",
          name: "Notes",
          description: "Notes",
          path: "notes",
          kind: "package",
          package_id: "package-1",
        }}
        canMutate={false}
        onClick={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "common.delete" }),
    ).not.toBeInTheDocument();
  });
});
