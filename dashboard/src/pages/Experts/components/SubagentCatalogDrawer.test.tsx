import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("./CatalogDrawer", () => ({
  default: ({ children, title }: { children: ReactNode; title: string }) => (
    <div data-testid="catalog-drawer" data-title={title}>
      {children}
    </div>
  ),
}));

const managerProps = vi.fn();
vi.mock("./SubagentManager", () => ({
  default: (props: { fillHeight?: boolean }) => {
    managerProps(props);
    return (
      <div
        data-testid="subagent-manager"
        data-fill-height={String(!!props.fillHeight)}
      />
    );
  },
}));

import SubagentCatalogDrawer from "./SubagentCatalogDrawer";

describe("SubagentCatalogDrawer", () => {
  beforeEach(() => {
    managerProps.mockClear();
  });

  it("enables fillHeight so the catalog can scroll on desktop (#136)", () => {
    const { container } = render(
      <SubagentCatalogDrawer
        agentId="ag_1"
        agentState="running"
        open
        installedSlugs={new Set()}
        onClose={() => undefined}
        onInstalled={() => undefined}
      />,
    );

    expect(screen.getByTestId("subagent-manager")).toHaveAttribute(
      "data-fill-height",
      "true",
    );
    expect(managerProps).toHaveBeenCalledWith(
      expect.objectContaining({ fillHeight: true }),
    );
    // Scroll shell must be a flex column with overflow:hidden so the
    // fillHeight child is height-bounded (nested overflow:auto alone breaks wheel).
    const shell = container.querySelector(
      "[data-testid='catalog-drawer'] > div",
    ) as HTMLElement | null;
    expect(shell).not.toBeNull();
    expect(shell!.style.display).toBe("flex");
    expect(shell!.style.flexDirection).toBe("column");
    expect(shell!.style.overflow).toBe("hidden");
    expect(shell!.style.minHeight).toMatch(/^0(px)?$/);
  });
});
