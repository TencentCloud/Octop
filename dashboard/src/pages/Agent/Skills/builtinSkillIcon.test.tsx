import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  builtinSkillIcon,
  resolveBuiltinSkillIcon,
  resolveFigurativeSkillIcon,
} from "./builtinSkillIcon";

function iconSrc(slug: string, emoji?: string): string {
  const { container } = render(<>{builtinSkillIcon(slug, 44, emoji)}</>);
  return container.querySelector("img")?.getAttribute("src") ?? "";
}

function figurativeSrc(
  slug: string,
  emoji?: string,
  name?: string,
): string | null {
  const visual = resolveFigurativeSkillIcon(slug, emoji, name);
  if (!visual) return null;
  const { container } = render(<>{visual.node}</>);
  return container.querySelector("img")?.getAttribute("src") ?? "";
}

describe("builtinSkillIcon", () => {
  it("renders a generated tile for skill-manager", () => {
    const src = iconSrc("skill-manager");
    expect(src).toContain("image/svg+xml");
    expect(resolveBuiltinSkillIcon("skill-manager").image).toBe(true);
  });

  it("gives leftover web-search a different tile", () => {
    const manager = iconSrc("skill-manager");
    const search = iconSrc("web-search", "🔍");
    expect(search).toContain("image/svg+xml");
    expect(search).not.toBe(manager);
  });

  it("keeps unknown builtin slugs on a stable hashed tile", () => {
    const first = iconSrc("alpha-skill");
    const again = iconSrc("alpha-skill");
    expect(first).toBe(again);
    expect(first).toContain("image/svg+xml");
  });

  it("uses a memory tile for 记忆管理 by name or slug", () => {
    const bySlug = figurativeSrc("memory-manager");
    const byName = figurativeSrc("custom-memory", undefined, "记忆管理");
    const byEmoji = figurativeSrc("notes", "🧠");
    expect(bySlug).toContain("image/svg+xml");
    expect(byName).toBe(bySlug);
    expect(byEmoji).toBe(bySlug);
    expect(bySlug).not.toBe(iconSrc("skill-manager"));
  });

  it("does not force a tile on unrelated workspace skills", () => {
    expect(resolveFigurativeSkillIcon("my-notes", undefined, "随手记")).toBe(
      null,
    );
  });
});
